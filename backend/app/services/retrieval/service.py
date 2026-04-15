"""Hybrid Retrieval 与重排服务。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import RetrievalCandidate, RetrievalRun, RerankResult
from app.models.kb import Document, DocumentChunk, DocumentEmbedding, DocumentFTS
from app.services.llm.dashscope_client import DashScopeClient


@dataclass(slots=True)
class RetrievedCandidate:
    """统一承载 dense / lexical / rerank 阶段的候选片段。"""

    chunk: DocumentChunk
    document_id: UUID
    dense_score: float | None = None
    lexical_score: float | None = None
    dense_rank: int | None = None
    lexical_rank: int | None = None
    hybrid_score: float = 0.0
    rerank_score: float | None = None
    alignment_score: float = 0.0
    final_score: float = 0.0
    parent_chunk: DocumentChunk | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def evidence_text(self) -> str:
        """返回用于回答阶段的证据文本。"""

        if self.parent_chunk is None or len(self.chunk.raw_text.strip()) >= 160:
            return self.chunk.contextualized_text

        parent_excerpt = self.parent_chunk.raw_text.strip()[:240]
        if not parent_excerpt:
            return self.chunk.contextualized_text
        return f"{self.chunk.contextualized_text}\n\n上级章节摘录:\n{parent_excerpt}"

    @property
    def rerank_text(self) -> str:
        """为重排构造更紧凑的证据文本，避免长上下文稀释问题焦点。"""

        section_text = " > ".join(str(item) for item in self.chunk.section_path) or "未命名章节"
        source_title = str(self.chunk.metadata_json.get("source_title", "")).strip()
        body_text = self.chunk.raw_text.strip()[:1200] or self.chunk.contextualized_text[:1200]
        return f"文档标题: {source_title}\n章节路径: {section_text}\n正文:\n{body_text}"


@dataclass(slots=True)
class RetrievalResult:
    """检索阶段输出。"""

    retrieval_run_id: UUID
    normalized_query: str
    candidates: list[RetrievedCandidate]
    usage: dict


class RetrievalService:
    """负责 dense + lexical + rerank 的统一编排。"""

    def __init__(self, db: Session, llm_client: DashScopeClient | None = None) -> None:
        self.db = db
        self.llm_client = llm_client or (DashScopeClient() if settings.has_dashscope_api_key else None)

    def retrieve(
        self,
        *,
        run_id: UUID,
        thread_id: UUID,
        workspace_id: UUID,
        query: str,
        document_ids: list[UUID] | None = None,
        dense_top_k: int = 12,
        lexical_top_k: int = 12,
        rerank_top_n: int = 6,
    ) -> RetrievalResult:
        """执行 dense、lexical、merge 与 rerank 的完整流程。"""

        normalized_query = " ".join(query.split())
        dense_candidates = self._dense_retrieve(
            workspace_id=workspace_id,
            query=normalized_query,
            document_ids=document_ids,
            top_k=dense_top_k,
        )
        lexical_candidates = self._lexical_retrieve(
            workspace_id=workspace_id,
            query=normalized_query,
            document_ids=document_ids,
            top_k=lexical_top_k,
        )
        merged_candidates = self._merge_candidates(dense_candidates=dense_candidates, lexical_candidates=lexical_candidates)
        self._attach_parent_chunks(merged_candidates)

        retrieval_run = RetrievalRun(
            run_id=run_id,
            thread_id=thread_id,
            workspace_id=workspace_id,
            query_text=query,
            rewritten_query=normalized_query,
            dense_top_k=dense_top_k,
            lexical_top_k=lexical_top_k,
            candidate_count=len(merged_candidates),
            metadata_json={"document_ids": [str(doc_id) for doc_id in document_ids or []]},
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(retrieval_run)
        self.db.flush()

        for rank_no, candidate in enumerate(merged_candidates, start=1):
            source_type = "hybrid"
            if candidate.dense_rank is not None and candidate.lexical_rank is None:
                source_type = "dense"
            elif candidate.lexical_rank is not None and candidate.dense_rank is None:
                source_type = "lexical"

            self.db.add(
                RetrievalCandidate(
                    retrieval_run_id=retrieval_run.id,
                    chunk_id=candidate.chunk.id,
                    document_id=candidate.document_id,
                    source_type=source_type,
                    rank_no=rank_no,
                    raw_score=candidate.hybrid_score,
                    merged_score=candidate.hybrid_score,
                    metadata_json={
                        "dense_score": candidate.dense_score,
                        "lexical_score": candidate.lexical_score,
                        "dense_rank": candidate.dense_rank,
                        "lexical_rank": candidate.lexical_rank,
                    },
                    created_at=datetime.now(timezone.utc),
                )
            )

        reranked_candidates, usage = self._rerank(
            query=normalized_query,
            retrieval_run_id=retrieval_run.id,
            candidates=merged_candidates,
            top_n=rerank_top_n,
        )
        return RetrievalResult(
            retrieval_run_id=retrieval_run.id,
            normalized_query=normalized_query,
            candidates=reranked_candidates,
            usage=usage,
        )

    def _dense_retrieve(
        self,
        *,
        workspace_id: UUID,
        query: str,
        document_ids: list[UUID] | None,
        top_k: int,
    ) -> list[RetrievedCandidate]:
        if self.llm_client is None:
            return []

        query_vector = self.llm_client.embed_texts([query])[0]
        distance_expr = DocumentEmbedding.embedding.cosine_distance(query_vector).label("distance")
        stmt = (
            select(DocumentChunk, distance_expr)
            .join(DocumentEmbedding, DocumentEmbedding.chunk_id == DocumentChunk.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
                Document.latest_version_id == DocumentChunk.document_version_id,
                DocumentChunk.chunk_level == "child",
            )
            .order_by(distance_expr.asc())
            .limit(top_k)
        )
        if document_ids:
            stmt = stmt.where(Document.id.in_(document_ids))

        rows = self.db.execute(stmt).all()
        candidates: list[RetrievedCandidate] = []
        for rank_no, (chunk, distance) in enumerate(rows, start=1):
            candidates.append(
                RetrievedCandidate(
                    chunk=chunk,
                    document_id=chunk.document_id,
                    dense_score=max(0.0, 1.0 - float(distance)),
                    dense_rank=rank_no,
                )
            )
        return candidates

    def _lexical_retrieve(
        self,
        *,
        workspace_id: UUID,
        query: str,
        document_ids: list[UUID] | None,
        top_k: int,
    ) -> list[RetrievedCandidate]:
        ts_query = func.websearch_to_tsquery("simple", query)
        rank_expr = func.ts_rank_cd(DocumentFTS.tsv, ts_query).label("rank_score")
        stmt = (
            select(DocumentChunk, rank_expr)
            .join(DocumentFTS, DocumentFTS.chunk_id == DocumentChunk.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
                Document.latest_version_id == DocumentChunk.document_version_id,
                DocumentChunk.chunk_level == "child",
                DocumentFTS.tsv.op("@@")(ts_query),
            )
            .order_by(rank_expr.desc())
            .limit(top_k)
        )
        if document_ids:
            stmt = stmt.where(Document.id.in_(document_ids))

        rows = self.db.execute(stmt).all()
        candidates: list[RetrievedCandidate] = []
        for rank_no, (chunk, rank_score) in enumerate(rows, start=1):
            candidates.append(
                RetrievedCandidate(
                    chunk=chunk,
                    document_id=chunk.document_id,
                    lexical_score=float(rank_score or 0.0),
                    lexical_rank=rank_no,
                )
            )
        return candidates

    def _merge_candidates(
        self,
        *,
        dense_candidates: list[RetrievedCandidate],
        lexical_candidates: list[RetrievedCandidate],
    ) -> list[RetrievedCandidate]:
        merged: dict[UUID, RetrievedCandidate] = {}
        rrf_k = 60.0

        for candidate in dense_candidates:
            merged[candidate.chunk.id] = candidate
            merged[candidate.chunk.id].hybrid_score += 1.0 / (rrf_k + (candidate.dense_rank or 1))

        for candidate in lexical_candidates:
            existing = merged.get(candidate.chunk.id)
            if existing is None:
                existing = candidate
                merged[candidate.chunk.id] = existing
            else:
                existing.lexical_score = candidate.lexical_score
                existing.lexical_rank = candidate.lexical_rank
            existing.hybrid_score += 1.0 / (rrf_k + (candidate.lexical_rank or 1))

        return sorted(merged.values(), key=lambda item: item.hybrid_score, reverse=True)[:12]

    def _attach_parent_chunks(self, candidates: list[RetrievedCandidate]) -> None:
        parent_ids = {candidate.chunk.parent_chunk_id for candidate in candidates if candidate.chunk.parent_chunk_id}
        if not parent_ids:
            return

        parent_rows = self.db.scalars(select(DocumentChunk).where(DocumentChunk.id.in_(parent_ids)))
        parent_map = {chunk.id: chunk for chunk in parent_rows}
        for candidate in candidates:
            if candidate.chunk.parent_chunk_id:
                candidate.parent_chunk = parent_map.get(candidate.chunk.parent_chunk_id)

    def _rerank(
        self,
        *,
        query: str,
        retrieval_run_id: UUID,
        candidates: list[RetrievedCandidate],
        top_n: int,
    ) -> tuple[list[RetrievedCandidate], dict]:
        if not candidates:
            return [], {}

        if self.llm_client is None:
            for candidate in candidates:
                candidate.alignment_score = self._compute_alignment_score(query, candidate)
                candidate.final_score = candidate.hybrid_score + candidate.alignment_score

            ordered = sorted(
                candidates,
                key=lambda item: (item.final_score, item.hybrid_score),
                reverse=True,
            )[:top_n]
            for index, candidate in enumerate(ordered, start=1):
                candidate.rerank_score = candidate.final_score
                self.db.add(
                    RerankResult(
                        retrieval_run_id=retrieval_run_id,
                        chunk_id=candidate.chunk.id,
                        rerank_model="hybrid_fallback",
                        rank_no=index,
                        rerank_score=candidate.final_score,
                        is_selected=True,
                        created_at=datetime.now(timezone.utc),
                    )
                )
            return ordered, {}

        documents = [candidate.rerank_text for candidate in candidates]
        rerank_items, usage = self.llm_client.rerank(query=query, documents=documents, top_n=len(documents))
        rerank_score_map = {item.index: item.relevance_score for item in rerank_items}

        for index, candidate in enumerate(candidates):
            candidate.rerank_score = rerank_score_map.get(index, 0.0)
            candidate.alignment_score = self._compute_alignment_score(query, candidate)
            candidate.final_score = self._compute_final_score(candidate)

        ordered = sorted(
            candidates,
            key=lambda item: (item.final_score, item.rerank_score or 0.0, item.hybrid_score),
            reverse=True,
        )[:top_n]
        for rank_no, candidate in enumerate(ordered, start=1):
            self.db.add(
                RerankResult(
                    retrieval_run_id=retrieval_run_id,
                    chunk_id=candidate.chunk.id,
                    rerank_model=f"{settings.rerank_model}+alignment_guard",
                    rank_no=rank_no,
                    rerank_score=candidate.rerank_score or candidate.final_score,
                    is_selected=True,
                    created_at=datetime.now(timezone.utc),
                )
            )
        return ordered, usage

    def _compute_final_score(self, candidate: RetrievedCandidate) -> float:
        """把模型重排分、精确匹配分和混合召回分合成为最终排序分。"""

        rerank_score = candidate.rerank_score or 0.0
        return rerank_score + candidate.alignment_score + (candidate.hybrid_score * 5.0)

    def _compute_alignment_score(self, query: str, candidate: RetrievedCandidate) -> float:
        """根据实体词和属性短语的显式命中情况，为精确问答补一层排序保护。"""

        fragments = self._extract_query_fragments(query)
        if not fragments:
            return 0.0

        section_text = " > ".join(str(item) for item in candidate.chunk.section_path).lower()
        body_text = candidate.chunk.raw_text.lower()
        lines = [line.strip().lower() for line in candidate.chunk.raw_text.splitlines() if line.strip()]
        if not lines:
            lines = [body_text]

        section_score = 0.0
        body_score = 0.0
        best_line_score = 0.0
        for fragment in fragments:
            weight = self._fragment_weight(fragment)
            if fragment in section_text:
                section_score += weight * 0.6
            if fragment in body_text:
                body_score += weight
            best_line_score = max(
                best_line_score,
                max((weight for line in lines if fragment in line), default=0.0),
            )

        return section_score + body_score + (best_line_score * 0.4)

    def _extract_query_fragments(self, query: str) -> list[str]:
        """从问题中提取更适合做精确匹配的实体词和属性短语。"""

        normalized_query = query.strip().lower()
        ascii_fragments = re.findall(r"[a-z][a-z0-9._-]*", normalized_query)

        chinese_source = re.sub(r"[a-z0-9._/-]+", " ", normalized_query)
        for pattern in (
            "请问",
            "一下",
            "是什么",
            "是多少次",
            "是多少天",
            "是多少",
            "有多少",
            "多少",
            "多久",
            "多大",
            "多长",
            "哪些",
            "哪个",
            "哪种",
            "哪类",
            "是否",
            "能否",
            "可否",
            "可以",
            "有无",
            "有没有",
            "分别是",
            "分别",
            "吗",
            "么",
            "呢",
            "？",
            "?",
        ):
            chinese_source = chinese_source.replace(pattern, " ")

        chinese_parts = [
            part.strip()
            for part in re.split(r"[，。！？；、\s]+|的", chinese_source)
            if part.strip()
        ]

        fragments: list[str] = []
        for fragment in [*ascii_fragments, *chinese_parts]:
            if len(fragment) < 2:
                continue
            if fragment not in fragments:
                fragments.append(fragment)
        return sorted(fragments, key=len, reverse=True)

    def _fragment_weight(self, fragment: str) -> float:
        """较长属性短语比通用词更重要，避免只命中套餐名就被误判为高相关。"""

        if fragment in {"套餐", "平台", "系统", "文档", "工作区"}:
            return 0.3
        if re.fullmatch(r"[a-z0-9._-]+", fragment):
            return 0.8 if len(fragment) >= 4 else 0.5
        if len(fragment) >= 6:
            return 1.2
        if len(fragment) >= 4:
            return 0.8
        return 0.5
