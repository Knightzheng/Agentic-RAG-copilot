"""长期记忆服务，负责语义记忆、情节记忆与程序性记忆。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.memory import (
    EpisodicMemory,
    EpisodicMemoryEmbedding,
    MemoryNamespace,
    ProceduralMemory,
    SemanticMemory,
    SemanticMemoryEmbedding,
)
from app.schemas.memory import MemoryCreate, MemoryRead, MemoryUpdate
from app.services.llm.dashscope_client import DashScopeClient


@dataclass(slots=True)
class RecalledMemory:
    """一次召回得到的长期记忆项。"""

    memory_type: str
    record_id: UUID
    title: str
    content_text: str
    summary_text: str | None
    score: float
    source_run_id: UUID | None
    source_thread_id: UUID | None
    is_pinned: bool
    metadata_json: dict


class MemoryService:
    """封装长期记忆的增删改查、召回与自动写入逻辑。"""

    def __init__(self, db: Session, llm_client: DashScopeClient | None = None) -> None:
        self.db = db
        self.llm_client = llm_client or (DashScopeClient() if settings.has_dashscope_api_key else None)

    def ensure_default_namespaces(self, *, workspace_id: UUID, user_id: UUID) -> dict[str, MemoryNamespace]:
        """在缺失时创建默认的语义、情节和程序性命名空间。"""

        existing = list(
            self.db.scalars(select(MemoryNamespace).where(MemoryNamespace.workspace_id == workspace_id))
        )
        namespace_map = {item.namespace_key: item for item in existing}
        defaults = {
            "semantic.default": ("Semantic Memory", "semantic", "Stable facts, aliases, and preferences."),
            "episodic.default": ("Episodic Memory", "episodic", "Past runs, outcomes, and lessons learned."),
            "procedural.default": ("Procedural Memory", "procedural", "Rules, strategies, and reusable instructions."),
        }
        created = False
        for key, (display_name, memory_type, description) in defaults.items():
            if key in namespace_map:
                continue
            namespace = MemoryNamespace(
                workspace_id=workspace_id,
                namespace_key=key,
                display_name=display_name,
                memory_type=memory_type,
                description=description,
                created_by=user_id,
                is_active=True,
                metadata_json={},
            )
            self.db.add(namespace)
            self.db.flush()
            namespace_map[key] = namespace
            created = True

        if created:
            self.db.flush()
        return namespace_map

    def list_memories(
        self,
        *,
        workspace_id: UUID,
        memory_type: str | None = None,
        query: str | None = None,
        pinned: bool | None = None,
        limit: int = 100,
    ) -> list[MemoryRead]:
        """列出当前工作区下所有受支持类型的长期记忆。"""

        records: list[MemoryRead] = []
        normalized_query = query.strip().lower() if query else ""
        for kind in self._memory_types(memory_type):
            for record in self._query_memory_model(kind, workspace_id=workspace_id, pinned=pinned):
                memory = self._memory_to_read(record, kind)
                if normalized_query and normalized_query not in f"{memory.title}\n{memory.content_text}\n{memory.summary_text or ''}".lower():
                    continue
                records.append(memory)

        return sorted(records, key=lambda item: item.updated_at, reverse=True)[:limit]

    def create_memory(self, payload: MemoryCreate) -> MemoryRead:
        """创建一条记忆，并在需要时补建索引。"""

        namespaces = self.ensure_default_namespaces(
            workspace_id=payload.workspace_id,
            user_id=payload.owner_user_id or settings.default_owner_user_id,
        )
        namespace = namespaces[f"{payload.memory_type}.default"]
        now = datetime.now(timezone.utc)

        if payload.memory_type == "semantic":
            record = SemanticMemory(
                namespace_id=namespace.id,
                workspace_id=payload.workspace_id,
                owner_user_id=payload.owner_user_id,
                title=payload.title,
                content_text=payload.content_text,
                summary_text=payload.summary_text,
                source_run_id=None,
                source_thread_id=None,
                confidence_score=payload.metadata_json.get("confidence_score"),
                is_pinned=False,
                is_active=True,
                metadata_json=payload.metadata_json,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(record)
            self.db.flush()
            self._refresh_semantic_embedding(record)
        elif payload.memory_type == "episodic":
            record = EpisodicMemory(
                namespace_id=namespace.id,
                workspace_id=payload.workspace_id,
                owner_user_id=payload.owner_user_id,
                title=payload.title,
                content_text=payload.content_text,
                summary_text=payload.summary_text,
                source_run_id=None,
                source_thread_id=None,
                outcome=payload.metadata_json.get("outcome"),
                is_pinned=False,
                is_active=True,
                metadata_json=payload.metadata_json,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(record)
            self.db.flush()
            self._refresh_episodic_embedding(record)
        elif payload.memory_type == "procedural":
            record = ProceduralMemory(
                namespace_id=namespace.id,
                workspace_id=payload.workspace_id,
                owner_user_id=payload.owner_user_id,
                title=payload.title,
                content_text=payload.content_text,
                summary_text=payload.summary_text,
                source_run_id=None,
                source_thread_id=None,
                priority=payload.priority or 100,
                is_pinned=False,
                is_active=True,
                metadata_json=payload.metadata_json,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(record)
            self.db.flush()
        else:
            raise ValueError("不支持的 memory_type")

        return self._memory_to_read(record, payload.memory_type)

    def update_memory(self, memory_id: UUID, payload: MemoryUpdate) -> MemoryRead:
        """更新一条记忆，并在内容变化后刷新 embedding。"""

        kind, record = self._get_memory_record(memory_id)
        if payload.title is not None:
            record.title = payload.title
        if payload.content_text is not None:
            record.content_text = payload.content_text
        if payload.summary_text is not None:
            record.summary_text = payload.summary_text
        if payload.is_active is not None:
            record.is_active = payload.is_active
        if payload.metadata_json is not None:
            record.metadata_json = payload.metadata_json
        if payload.priority is not None and hasattr(record, "priority"):
            record.priority = payload.priority
        record.updated_at = datetime.now(timezone.utc)
        self.db.flush()

        if kind == "semantic":
            self._refresh_semantic_embedding(record)
        elif kind == "episodic":
            self._refresh_episodic_embedding(record)
        return self._memory_to_read(record, kind)

    def set_pinned(self, memory_id: UUID, *, pinned: bool) -> MemoryRead:
        """切换一条记忆的固定状态。"""

        kind, record = self._get_memory_record(memory_id)
        record.is_pinned = pinned
        record.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return self._memory_to_read(record, kind)

    def delete_memory(self, memory_id: UUID) -> None:
        """软删除一条记忆。"""

        kind, record = self._get_memory_record(memory_id)
        record.deleted_at = datetime.now(timezone.utc)
        record.is_active = False
        record.updated_at = datetime.now(timezone.utc)
        if kind == "semantic":
            self.db.query(SemanticMemoryEmbedding).filter(SemanticMemoryEmbedding.memory_id == record.id).delete()
        elif kind == "episodic":
            self.db.query(EpisodicMemoryEmbedding).filter(EpisodicMemoryEmbedding.memory_id == record.id).delete()
        self.db.flush()

    def recall_memories(self, *, workspace_id: UUID, query: str, limit: int = 6) -> list[dict]:
        """召回与当前问题相关的长期记忆。"""

        normalized_query = " ".join(query.split())
        if not normalized_query:
            return []
        recalled: list[RecalledMemory] = []
        query_vector = self.llm_client.embed_texts([normalized_query])[0] if self.llm_client is not None else None
        if query_vector is not None:
            recalled.extend(self._recall_semantic_memories(workspace_id=workspace_id, query_vector=query_vector))
            recalled.extend(self._recall_episodic_memories(workspace_id=workspace_id, query_vector=query_vector))
        recalled.extend(
            self._recall_lexical_memories(workspace_id=workspace_id, kind="semantic", query=normalized_query)
        )
        recalled.extend(
            self._recall_lexical_memories(workspace_id=workspace_id, kind="episodic", query=normalized_query)
        )
        recalled.extend(self._recall_procedural_memories(workspace_id=workspace_id, query=normalized_query))

        deduped: dict[tuple[str, UUID], RecalledMemory] = {}
        for item in recalled:
            if self._is_noise_memory_payload(item):
                continue
            key = (item.memory_type, item.record_id)
            existing = deduped.get(key)
            if existing is None or item.score > existing.score:
                deduped[key] = item

        ordered = sorted(
            deduped.values(),
            key=lambda item: (item.score + (0.2 if item.is_pinned else 0.0), item.is_pinned),
            reverse=True,
        )[:limit]
        return [
            {
                "id": str(item.record_id),
                "memory_type": item.memory_type,
                "title": item.title,
                "content_text": item.content_text,
                "summary_text": item.summary_text,
                "score": round(item.score, 4),
                "source_run_id": str(item.source_run_id) if item.source_run_id else None,
                "source_thread_id": str(item.source_thread_id) if item.source_thread_id else None,
                "is_pinned": item.is_pinned,
                "metadata_json": item.metadata_json,
            }
            for item in ordered
        ]

    def maybe_write_semantic_memory(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        thread_id: UUID,
        run_id: UUID,
        user_message: str,
    ) -> MemoryRead | None:
        """当用户明确要求“记住”时写入语义记忆。"""

        extracted = self._extract_explicit_memory_text(user_message)
        if not extracted:
            return None

        namespaces = self.ensure_default_namespaces(workspace_id=workspace_id, user_id=user_id)
        existing = self.db.scalar(
            select(SemanticMemory).where(
                SemanticMemory.workspace_id == workspace_id,
                SemanticMemory.deleted_at.is_(None),
                SemanticMemory.content_text == extracted,
            )
        )
        if existing is not None:
            existing.source_run_id = run_id
            existing.source_thread_id = thread_id
            existing.updated_at = datetime.now(timezone.utc)
            self.db.flush()
            self._refresh_semantic_embedding(existing)
            return self._memory_to_read(existing, "semantic")

        now = datetime.now(timezone.utc)
        record = SemanticMemory(
            namespace_id=namespaces["semantic.default"].id,
            workspace_id=workspace_id,
            owner_user_id=user_id,
            title=self._build_memory_title(extracted),
            content_text=extracted,
            summary_text=extracted[:240],
            source_run_id=run_id,
            source_thread_id=thread_id,
            confidence_score=0.95,
            is_pinned=False,
            is_active=True,
            metadata_json={"source": "explicit_user_memory"},
            deleted_at=None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        self.db.flush()
        self._refresh_semantic_embedding(record)
        return self._memory_to_read(record, "semantic")

    def maybe_write_episodic_memory(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        thread_id: UUID,
        run_id: UUID,
        question: str,
        answer: str,
        result_status: str,
        evidence_grade: str | None,
        request_type: str | None = None,
        route_target: str | None = None,
    ) -> MemoryRead | None:
        """从一次已完成运行中沉淀一条紧凑的情节记忆。"""

        if not self._should_write_episodic_memory(
            result_status=result_status,
            request_type=request_type,
            route_target=route_target,
            answer=answer,
        ):
            return None

        namespaces = self.ensure_default_namespaces(workspace_id=workspace_id, user_id=user_id)
        now = datetime.now(timezone.utc)
        content_text = f"Q: {question.strip()}\nA: {answer.strip()}"
        record = EpisodicMemory(
            namespace_id=namespaces["episodic.default"].id,
            workspace_id=workspace_id,
            owner_user_id=user_id,
            title=self._build_memory_title(question),
            content_text=content_text,
            summary_text=answer.strip()[:240],
            source_run_id=run_id,
            source_thread_id=thread_id,
            outcome=result_status,
            is_pinned=False,
            is_active=True,
            metadata_json={"evidence_grade": evidence_grade},
            deleted_at=None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        self.db.flush()
        self._refresh_episodic_embedding(record)
        return self._memory_to_read(record, "episodic")

    @classmethod
    def _should_write_episodic_memory(
        cls,
        *,
        result_status: str,
        request_type: str | None,
        route_target: str | None,
        answer: str,
    ) -> bool:
        if result_status != "success":
            return False
        if request_type in {"memory", "context_update"}:
            return False
        if route_target == "direct" and request_type not in {"event_memory"}:
            return False
        if not answer.strip():
            return False
        if cls._is_noise_memory_text(answer):
            return False
        return True

    def cleanup_noisy_memories(self, *, workspace_id: UUID) -> dict[str, int]:
        """在指定工作区内软删除明显异常或低价值的记忆。"""

        deleted = {"semantic": 0, "episodic": 0, "procedural": 0}
        for kind in ("semantic", "episodic", "procedural"):
            model = self._memory_model(kind)
            rows = list(
                self.db.scalars(select(model).where(model.workspace_id == workspace_id, model.deleted_at.is_(None)))
            )
            for row in rows:
                if not self._should_cleanup_memory_record(kind=kind, record=row):
                    continue
                row.deleted_at = datetime.now(timezone.utc)
                row.is_active = False
                row.updated_at = datetime.now(timezone.utc)
                if kind == "semantic":
                    self.db.query(SemanticMemoryEmbedding).filter(SemanticMemoryEmbedding.memory_id == row.id).delete()
                elif kind == "episodic":
                    self.db.query(EpisodicMemoryEmbedding).filter(EpisodicMemoryEmbedding.memory_id == row.id).delete()
                deleted[kind] += 1

        self.db.flush()
        return deleted

    def _query_memory_model(
        self,
        kind: str,
        *,
        workspace_id: UUID,
        pinned: bool | None,
    ):
        model = self._memory_model(kind)
        stmt: Select = select(model).where(model.workspace_id == workspace_id, model.deleted_at.is_(None))
        if pinned is not None:
            stmt = stmt.where(model.is_pinned.is_(pinned))
        if hasattr(model, "priority"):
            stmt = stmt.order_by(model.is_pinned.desc(), model.priority.asc(), model.updated_at.desc())
        else:
            stmt = stmt.order_by(model.is_pinned.desc(), model.updated_at.desc())
        return list(self.db.scalars(stmt))

    def _get_memory_record(self, memory_id: UUID):
        for kind in ("semantic", "episodic", "procedural"):
            model = self._memory_model(kind)
            record = self.db.scalar(select(model).where(model.id == memory_id, model.deleted_at.is_(None)))
            if record is not None:
                return kind, record
        raise ValueError("记忆不存在")

    def _memory_model(self, kind: str):
        if kind == "semantic":
            return SemanticMemory
        if kind == "episodic":
            return EpisodicMemory
        if kind == "procedural":
            return ProceduralMemory
        raise ValueError("不支持的 memory_type")

    def _memory_types(self, requested: str | None) -> tuple[str, ...]:
        if requested in {None, "", "all"}:
            return ("semantic", "episodic", "procedural")
        if requested not in {"semantic", "episodic", "procedural"}:
            raise ValueError("不支持的 memory_type")
        return (requested,)

    def _memory_to_read(self, record, kind: str, score: float | None = None) -> MemoryRead:
        return MemoryRead(
            id=record.id,
            workspace_id=record.workspace_id,
            memory_type=kind,
            title=record.title,
            content_text=record.content_text,
            summary_text=record.summary_text,
            source_run_id=record.source_run_id,
            source_thread_id=record.source_thread_id,
            owner_user_id=record.owner_user_id,
            priority=getattr(record, "priority", None),
            confidence_score=getattr(record, "confidence_score", None),
            score=score,
            is_pinned=record.is_pinned,
            is_active=record.is_active,
            metadata_json=record.metadata_json or {},
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _refresh_semantic_embedding(self, record: SemanticMemory) -> None:
        if self.llm_client is None:
            return
        text = f"{record.title}\n{record.content_text}"
        embedding = self.llm_client.embed_texts([text])[0]
        self.db.query(SemanticMemoryEmbedding).filter(SemanticMemoryEmbedding.memory_id == record.id).delete()
        self.db.add(
            SemanticMemoryEmbedding(
                workspace_id=record.workspace_id,
                memory_id=record.id,
                model_name=settings.embedding_model,
                embedding_dim=settings.embedding_dimensions,
                embedding=embedding,
                text_hash=self._text_hash(text),
                created_at=datetime.now(timezone.utc),
            )
        )
        self.db.flush()

    def _refresh_episodic_embedding(self, record: EpisodicMemory) -> None:
        if self.llm_client is None:
            return
        text = f"{record.title}\n{record.content_text}"
        embedding = self.llm_client.embed_texts([text])[0]
        self.db.query(EpisodicMemoryEmbedding).filter(EpisodicMemoryEmbedding.memory_id == record.id).delete()
        self.db.add(
            EpisodicMemoryEmbedding(
                workspace_id=record.workspace_id,
                memory_id=record.id,
                model_name=settings.embedding_model,
                embedding_dim=settings.embedding_dimensions,
                embedding=embedding,
                text_hash=self._text_hash(text),
                created_at=datetime.now(timezone.utc),
            )
        )
        self.db.flush()

    def _recall_semantic_memories(self, *, workspace_id: UUID, query_vector: list[float]) -> list[RecalledMemory]:
        distance_expr = SemanticMemoryEmbedding.embedding.cosine_distance(query_vector).label("distance")
        stmt = (
            select(SemanticMemory, distance_expr)
            .join(SemanticMemoryEmbedding, SemanticMemoryEmbedding.memory_id == SemanticMemory.id)
            .where(
                SemanticMemory.workspace_id == workspace_id,
                SemanticMemory.deleted_at.is_(None),
                SemanticMemory.is_active.is_(True),
            )
            .order_by(distance_expr.asc())
            .limit(4)
        )
        rows = self.db.execute(stmt).all()
        return [
            RecalledMemory(
                memory_type="semantic",
                record_id=memory.id,
                title=memory.title,
                content_text=memory.content_text,
                summary_text=memory.summary_text,
                score=max(0.0, 1.0 - float(distance)),
                source_run_id=memory.source_run_id,
                source_thread_id=memory.source_thread_id,
                is_pinned=memory.is_pinned,
                metadata_json=memory.metadata_json or {},
            )
            for memory, distance in rows
        ]

    def _recall_episodic_memories(self, *, workspace_id: UUID, query_vector: list[float]) -> list[RecalledMemory]:
        distance_expr = EpisodicMemoryEmbedding.embedding.cosine_distance(query_vector).label("distance")
        stmt = (
            select(EpisodicMemory, distance_expr)
            .join(EpisodicMemoryEmbedding, EpisodicMemoryEmbedding.memory_id == EpisodicMemory.id)
            .where(
                EpisodicMemory.workspace_id == workspace_id,
                EpisodicMemory.deleted_at.is_(None),
                EpisodicMemory.is_active.is_(True),
            )
            .order_by(distance_expr.asc())
            .limit(4)
        )
        rows = self.db.execute(stmt).all()
        return [
            RecalledMemory(
                memory_type="episodic",
                record_id=memory.id,
                title=memory.title,
                content_text=memory.content_text,
                summary_text=memory.summary_text,
                score=max(0.0, 1.0 - float(distance)),
                source_run_id=memory.source_run_id,
                source_thread_id=memory.source_thread_id,
                is_pinned=memory.is_pinned,
                metadata_json=memory.metadata_json or {},
            )
            for memory, distance in rows
        ]

    def _recall_procedural_memories(self, *, workspace_id: UUID, query: str) -> list[RecalledMemory]:
        stmt = (
            select(ProceduralMemory)
            .where(
                ProceduralMemory.workspace_id == workspace_id,
                ProceduralMemory.deleted_at.is_(None),
                ProceduralMemory.is_active.is_(True),
            )
            .order_by(ProceduralMemory.is_pinned.desc(), ProceduralMemory.priority.asc(), ProceduralMemory.updated_at.desc())
            .limit(20)
        )
        recalled: list[RecalledMemory] = []
        for memory in self.db.scalars(stmt):
            haystack = f"{memory.title}\n{memory.content_text}\n{memory.summary_text or ''}".lower()
            score = self._score_procedural_memory(query=query, haystack=haystack, is_pinned=memory.is_pinned)
            if score <= 0:
                continue
            recalled.append(
                RecalledMemory(
                    memory_type="procedural",
                    record_id=memory.id,
                    title=memory.title,
                    content_text=memory.content_text,
                    summary_text=memory.summary_text,
                    score=score,
                    source_run_id=memory.source_run_id,
                    source_thread_id=memory.source_thread_id,
                    is_pinned=memory.is_pinned,
                    metadata_json=memory.metadata_json or {},
                )
            )
        return recalled[:4]

    @classmethod
    def _score_procedural_memory(cls, *, query: str, haystack: str, is_pinned: bool) -> float:
        score = 0.0
        for fragment in cls._extract_query_fragments(query):
            if fragment in haystack:
                score += 0.8 if len(fragment) >= 4 else 0.4

        if cls._looks_like_kb_question(query) and cls._looks_like_kb_rule(haystack):
            score += 1.1

        if is_pinned:
            score += 0.3
        return score

    def _recall_lexical_memories(self, *, workspace_id: UUID, kind: str, query: str) -> list[RecalledMemory]:
        fragments = self._extract_query_fragments(query)
        if not fragments:
            return []

        model = self._memory_model(kind)
        stmt = (
            select(model)
            .where(
                model.workspace_id == workspace_id,
                model.deleted_at.is_(None),
                model.is_active.is_(True),
            )
            .order_by(model.is_pinned.desc(), model.updated_at.desc())
            .limit(20)
        )
        recalled: list[RecalledMemory] = []
        for memory in self.db.scalars(stmt):
            haystack = f"{memory.title}\n{memory.content_text}\n{memory.summary_text or ''}".lower()
            score = 0.0
            for fragment in fragments:
                if fragment in haystack:
                    score += 0.8 if len(fragment) >= 4 else 0.4
            if memory.is_pinned:
                score += 0.2
            if score <= 0:
                continue
            recalled.append(
                RecalledMemory(
                    memory_type=kind,
                    record_id=memory.id,
                    title=memory.title,
                    content_text=memory.content_text,
                    summary_text=memory.summary_text,
                    score=score,
                    source_run_id=memory.source_run_id,
                    source_thread_id=memory.source_thread_id,
                    is_pinned=memory.is_pinned,
                    metadata_json=memory.metadata_json or {},
                )
            )
        return recalled[:4]

    @staticmethod
    def _extract_explicit_memory_text(message: str) -> str | None:
        normalized = " ".join(message.split()).strip()
        if not normalized:
            return None
        patterns = (
            r"^(?:请|麻烦|请你|帮我|麻烦你)?记住(?:一下)?[:：]?\s*(.+)$",
            r"^(?:请|麻烦|请你|帮我|麻烦你)?记一下[:：]?\s*(.+)$",
            r"^以后请按这个记[:：]?\s*(.+)$",
        )
        for pattern in patterns:
            match = re.match(pattern, normalized, re.I)
            if match:
                content = match.group(1).strip("。；; ")
                return content or None
        return None

    @staticmethod
    def _is_noise_memory_text(text: str) -> bool:
        normalized = " ".join(text.split()).strip()
        if not normalized:
            return True

        noisy_prefixes = (
            "根据当前知识库中的证据",
            "当前没有足够信息生成最终回答",
            "已记住：",
            "已记住:",
            "我当前记住的要点是",
            "我目前能从当前线程背景中确认这些要点",
            "我目前还没有检索到明确的长期记忆",
            "当前线程里还没有足够的项目背景信息",
            "我目前还没有检索到与这一轮新增内容相关的明确事件记忆",
        )
        if any(normalized.startswith(prefix) for prefix in noisy_prefixes):
            return True

        if normalized in {"了我的什么回答偏好？", "了我的什么回答偏好?"}:
            return True

        return False

    def _is_noise_memory_payload(self, item: RecalledMemory) -> bool:
        if self._is_noise_memory_text(item.summary_text or item.content_text or ""):
            return True
        if item.memory_type == "semantic" and self._looks_like_question(item.title):
            return True
        if item.memory_type == "episodic":
            if self._looks_like_question(item.summary_text or "") and self._looks_like_question(item.title):
                return True
            if str((item.metadata_json or {}).get("evidence_grade") or "") == "insufficient":
                return True
        return False

    def _should_cleanup_memory_record(self, *, kind: str, record: object) -> bool:
        title = str(getattr(record, "title", "") or "").strip()
        content = str(getattr(record, "content_text", "") or "").strip()
        summary = str(getattr(record, "summary_text", "") or "").strip()
        metadata = getattr(record, "metadata_json", {}) or {}

        if self._is_noise_memory_text(summary or content):
            return True
        if kind == "semantic" and self._looks_like_question(title):
            return True
        if kind == "episodic":
            if str(metadata.get("evidence_grade") or "") == "insufficient":
                return True
            if title.startswith("你记住了") or title.startswith("我之前说过"):
                return True
        return False

    @staticmethod
    def _looks_like_question(text: str) -> bool:
        normalized = " ".join(text.split()).strip()
        if not normalized:
            return False
        markers = ("？", "?", "什么", "吗", "么", "哪", "如何", "为什么")
        return normalized.endswith(("？", "?")) or any(marker in normalized for marker in markers)

    @staticmethod
    def _build_memory_title(text: str) -> str:
        clean = " ".join(text.split()).strip()
        return clean[:80] if len(clean) > 80 else clean

    @staticmethod
    def _text_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_query_fragments(query: str) -> list[str]:
        ascii_fragments = re.findall(r"[a-z][a-z0-9._-]*", query.lower())
        chinese_parts = [part.strip() for part in re.split(r"[，。！？；、\s]+", query) if len(part.strip()) >= 2]
        fragments: list[str] = []
        for fragment in [*ascii_fragments, *chinese_parts]:
            if fragment not in fragments:
                fragments.append(fragment.lower())
        return sorted(fragments, key=len, reverse=True)

    @staticmethod
    def _looks_like_kb_question(query: str) -> bool:
        normalized = " ".join(query.lower().split())
        kb_markers = (
            "starter",
            "business",
            "enterprise",
            "viewer",
            "owner",
            "editor",
            "mcp",
            "memory center",
            "套餐",
            "模块",
            "知识库",
            "文档",
            "工作区",
            "单文件",
            "上限",
            "运行日志",
            "导出引用",
        )
        return any(marker in normalized for marker in kb_markers)

    @staticmethod
    def _looks_like_kb_rule(haystack: str) -> bool:
        rule_markers = (
            "知识库",
            "citation",
            "citations",
            "引用",
            "证据",
            "先给结论",
            "先给答案",
            "不要展开",
            "简洁",
            "grounded",
        )
        return any(marker in haystack for marker in rule_markers)
