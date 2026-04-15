"""运行七组记忆能力自动回归，并在结束后清理临时数据。"""

from __future__ import annotations

import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.agent import (
    AgentRun,
    AgentRunStep,
    Citation,
    EvidenceAssessment,
    Message,
    RetrievalCandidate,
    RetrievalRun,
    RerankResult,
    RunStateSnapshot,
    Thread,
)
from app.models.core import Workspace, WorkspaceMember
from app.models.kb import Document, DocumentBlock, DocumentChunk, DocumentEmbedding, DocumentFTS, DocumentVersion
from app.models.memory import (
    EpisodicMemory,
    EpisodicMemoryEmbedding,
    MemoryNamespace,
    ProceduralMemory,
    SemanticMemory,
    SemanticMemoryEmbedding,
)


KB_SAMPLE_PATH = PROJECT_ROOT / "atlas_agentic_rag_testset_v1" / "atlas_kb_test_corpus_v1.md"


@dataclass(slots=True)
class CaseResult:
    """单组回归结果。"""

    name: str
    passed: bool
    details: list[str]


class RegressionFailure(RuntimeError):
    """用于中断单组回归并汇总失败原因。"""


class RegressionClient:
    """对 FastAPI 接口做最小包装，便于模拟前端输入。"""

    def __init__(self) -> None:
        self.client = TestClient(app)

    def create_workspace(self, name: str) -> dict[str, Any]:
        slug = f"memory-reg-{uuid4().hex[:10]}"
        response = self.client.post(
            f"{settings.api_prefix}/workspaces",
            json={
                "name": name,
                "slug": slug,
                "description": "自动记忆回归临时工作区",
                "owner_user_id": str(settings.default_owner_user_id),
                "visibility": "private",
                "settings_json": {},
            },
        )
        self._expect_status(response, 201, "创建工作区失败")
        return response.json()

    def upload_document(self, workspace_id: UUID, path: Path) -> dict[str, Any]:
        with path.open("rb") as handle:
            response = self.client.post(
                f"{settings.api_prefix}/documents/upload",
                files={"file": (path.name, handle, "text/markdown")},
                data={
                    "workspace_id": str(workspace_id),
                    "owner_user_id": str(settings.default_owner_user_id),
                },
            )
        self._expect_status(response, 201, "上传测试文档失败")
        return response.json()

    def chat(
        self,
        *,
        workspace_id: UUID,
        message: str,
        thread_id: UUID | None = None,
        attachments: list[UUID] | None = None,
        mode: str = "auto",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "workspace_id": str(workspace_id),
            "message": message,
            "mode": mode,
            "attachments": [str(item) for item in (attachments or [])],
            "metadata": metadata or {},
            "user_id": str(settings.default_owner_user_id),
        }
        if thread_id is not None:
            payload["thread_id"] = str(thread_id)
        response = self.client.post(f"{settings.api_prefix}/chat", json=payload)
        self._expect_status(response, 200, f"聊天失败: {message}")
        return response.json()

    def get_thread(self, thread_id: UUID) -> dict[str, Any]:
        response = self.client.get(f"{settings.api_prefix}/threads/{thread_id}")
        self._expect_status(response, 200, "读取线程详情失败")
        return response.json()

    def list_memory(
        self,
        *,
        workspace_id: UUID,
        memory_type: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"workspace_id": str(workspace_id), "limit": 100}
        if memory_type:
            params["memory_type"] = memory_type
        if query:
            params["query"] = query
        response = self.client.get(f"{settings.api_prefix}/memory", params=params)
        self._expect_status(response, 200, "读取记忆列表失败")
        return response.json()

    def create_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(f"{settings.api_prefix}/memory", json=payload)
        self._expect_status(response, 200, "创建记忆失败")
        return response.json()

    def get_run_trace(self, run_id: UUID) -> dict[str, Any]:
        response = self.client.get(f"{settings.api_prefix}/runs/{run_id}/trace")
        self._expect_status(response, 200, "读取 Trace 失败")
        return response.json()

    @staticmethod
    def _expect_status(response: Any, expected: int, message: str) -> None:
        if response.status_code != expected:
            raise RegressionFailure(f"{message}: {response.status_code} {response.text}")


def cleanup_workspace(workspace_id: UUID) -> None:
    """删除临时工作区及其关联数据，并清理本地存储。"""

    db = SessionLocal()
    try:
        run_ids = select(AgentRun.id).where(AgentRun.workspace_id == workspace_id)
        thread_ids = select(Thread.id).where(Thread.workspace_id == workspace_id)
        document_ids = select(Document.id).where(Document.workspace_id == workspace_id)
        version_ids = select(DocumentVersion.id).where(DocumentVersion.document_id.in_(document_ids))
        semantic_ids = select(SemanticMemory.id).where(SemanticMemory.workspace_id == workspace_id)
        episodic_ids = select(EpisodicMemory.id).where(EpisodicMemory.workspace_id == workspace_id)

        db.execute(delete(SemanticMemoryEmbedding).where(SemanticMemoryEmbedding.workspace_id == workspace_id))
        db.execute(delete(EpisodicMemoryEmbedding).where(EpisodicMemoryEmbedding.workspace_id == workspace_id))
        db.execute(delete(ProceduralMemory).where(ProceduralMemory.workspace_id == workspace_id))
        db.execute(delete(SemanticMemory).where(SemanticMemory.workspace_id == workspace_id))
        db.execute(delete(EpisodicMemory).where(EpisodicMemory.workspace_id == workspace_id))
        db.execute(delete(MemoryNamespace).where(MemoryNamespace.workspace_id == workspace_id))

        db.execute(delete(Citation).where(Citation.run_id.in_(run_ids)))
        db.execute(delete(EvidenceAssessment).where(EvidenceAssessment.run_id.in_(run_ids)))
        db.execute(delete(RerankResult).where(RerankResult.retrieval_run_id.in_(select(RetrievalRun.id).where(RetrievalRun.workspace_id == workspace_id))))
        db.execute(delete(RetrievalCandidate).where(RetrievalCandidate.retrieval_run_id.in_(select(RetrievalRun.id).where(RetrievalRun.workspace_id == workspace_id))))
        db.execute(delete(RetrievalRun).where(RetrievalRun.workspace_id == workspace_id))
        db.execute(delete(AgentRunStep).where(AgentRunStep.run_id.in_(run_ids)))
        db.execute(delete(RunStateSnapshot).where(RunStateSnapshot.run_id.in_(run_ids)))
        db.execute(delete(AgentRun).where(AgentRun.workspace_id == workspace_id))

        db.execute(delete(DocumentEmbedding).where(DocumentEmbedding.workspace_id == workspace_id))
        db.execute(delete(DocumentFTS).where(DocumentFTS.workspace_id == workspace_id))
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id.in_(document_ids)))
        db.execute(delete(DocumentBlock).where(DocumentBlock.document_version_id.in_(version_ids)))
        db.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(document_ids)))
        db.execute(delete(Document).where(Document.workspace_id == workspace_id))

        db.execute(delete(Message).where(Message.thread_id.in_(thread_ids)))
        db.execute(delete(Thread).where(Thread.workspace_id == workspace_id))
        db.execute(delete(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))
        db.execute(delete(Workspace).where(Workspace.id == workspace_id))
        db.commit()
    finally:
        db.close()

    storage_root = (PROJECT_ROOT / settings.local_storage_root).resolve()
    workspace_dir = storage_root / str(workspace_id)
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir, ignore_errors=True)


def _contains_all(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return all(term.lower() in lowered for term in terms)


def _contains_none(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return all(term.lower() not in lowered for term in terms)


def _require(condition: bool, message: str, details: list[str]) -> None:
    if not condition:
        details.append(f"失败: {message}")
        raise RegressionFailure(message)
    details.append(f"通过: {message}")


def _wait_for_trace_steps(
    client: RegressionClient,
    *,
    run_id: UUID,
    step_key: str,
    retries: int = 5,
    interval_seconds: float = 0.4,
) -> list[dict[str, Any]]:
    last_steps: list[dict[str, Any]] = []
    for _ in range(retries):
        trace = client.get_run_trace(run_id)
        last_steps = [item for item in trace["steps"] if item["step_key"] == step_key]
        if last_steps:
            return last_steps
        time.sleep(interval_seconds)
    return last_steps


def _wait_for_recalled_memories(
    client: RegressionClient,
    *,
    run_id: UUID,
    step_key: str = "recall_long_term_memory",
    retries: int = 6,
    interval_seconds: float = 0.4,
) -> list[dict[str, Any]]:
    last_payload: list[dict[str, Any]] = []
    for _ in range(retries):
        steps = _wait_for_trace_steps(
            client,
            run_id=run_id,
            step_key=step_key,
            retries=1,
            interval_seconds=interval_seconds,
        )
        if steps:
            payload = steps[-1]["output_json"].get("recalled_memories", [])
            if payload:
                return payload
            last_payload = payload
        time.sleep(interval_seconds)
    return last_payload


def case_semantic_memory(client: RegressionClient) -> CaseResult:
    workspace = client.create_workspace("语义记忆写入与回忆")
    workspace_id = UUID(workspace["id"])
    details: list[str] = [f"工作区: {workspace_id}"]
    try:
        first = client.chat(workspace_id=workspace_id, message="请记住：我偏好中文回答，且默认先给结论再给原因。")
        recall_same = client.chat(
            workspace_id=workspace_id,
            thread_id=UUID(first["thread_id"]),
            message="你记住了我的什么回答偏好？",
        )
        recall_new = client.chat(workspace_id=workspace_id, message="我的默认回答偏好是什么？")
        semantics = client.list_memory(workspace_id=workspace_id, memory_type="semantic")

        _require("已记住" in first["answer"], "显式记忆写入得到确认", details)
        _require(
            _contains_all(recall_same["answer"], ["中文", "结论", "原因"]),
            "同线程回忆命中中文回答与先结论后原因",
            details,
        )
        _require(
            _contains_all(recall_new["answer"], ["中文", "结论", "原因"]),
            "新线程回忆命中语义记忆",
            details,
        )
        _require(
            any(_contains_all(item.get("content_text", ""), ["中文", "结论", "原因"]) for item in semantics),
            "语义记忆已写入记忆中心",
            details,
        )
        return CaseResult(name="1. 显式语义记忆写入", passed=True, details=details)
    except RegressionFailure as exc:
        details.append(f"异常: {exc}")
        return CaseResult(name="1. 显式语义记忆写入", passed=False, details=details)
    finally:
        cleanup_workspace(workspace_id)


def case_combined_preferences(client: RegressionClient) -> CaseResult:
    workspace = client.create_workspace("多条偏好合并")
    workspace_id = UUID(workspace["id"])
    details: list[str] = [f"工作区: {workspace_id}"]
    try:
        first = client.chat(workspace_id=workspace_id, message="请记住：除非我明确要求，否则不要给我长代码块。")
        second = client.chat(
            workspace_id=workspace_id,
            thread_id=UUID(first["thread_id"]),
            message="请记住：如果能在 3 句话内讲清，就不要展开。",
        )
        recall = client.chat(
            workspace_id=workspace_id,
            thread_id=UUID(second["thread_id"]),
            message="你记住了我目前哪些回答偏好？",
        )

        _require(
            _contains_all(recall["answer"], ["长代码块", "3 句话"]),
            "回答同时覆盖两条新增偏好",
            details,
        )
        return CaseResult(name="2. 多条偏好合并记忆", passed=True, details=details)
    except RegressionFailure as exc:
        details.append(f"异常: {exc}")
        return CaseResult(name="2. 多条偏好合并记忆", passed=False, details=details)
    finally:
        cleanup_workspace(workspace_id)


def case_thread_summary(client: RegressionClient) -> CaseResult:
    workspace = client.create_workspace("线程背景压缩")
    workspace_id = UUID(workspace["id"])
    details: list[str] = [f"工作区: {workspace_id}"]
    try:
        thread_id: UUID | None = None
        statements = [
            "我的项目是 Agentic RAG。",
            "后端是 FastAPI。",
            "前端是 React。",
            "数据库是 PostgreSQL。",
            "模型是 qwen3-max、text-embedding-v4、qwen3-rerank。",
            "第一版部署是本地存储 + 本地 PostgreSQL + 可选 Redis。",
            "我当前最关注多轮会话和 memory。",
        ]
        for statement in statements:
            result = client.chat(workspace_id=workspace_id, thread_id=thread_id, message=statement)
            thread_id = UUID(result["thread_id"])

        summary_answer = client.chat(
            workspace_id=workspace_id,
            thread_id=thread_id,
            message="请总结一下我当前项目的关键背景。",
        )
        thread_detail = client.get_thread(thread_id)
        thread_summary = thread_detail.get("thread_summary") or ""

        _require(bool(thread_summary.strip()), "线程摘要已生成", details)
        _require(
            _contains_all(summary_answer["answer"], ["Agentic RAG", "FastAPI", "React", "PostgreSQL"]),
            "项目背景总结命中核心技术栈",
            details,
        )
        _require(
            _contains_all(thread_summary, ["FastAPI", "React"]),
            "压缩背景中保留近期关键事实",
            details,
        )
        return CaseResult(name="3. 线程背景压缩", passed=True, details=details)
    except RegressionFailure as exc:
        details.append(f"异常: {exc}")
        return CaseResult(name="3. 线程背景压缩", passed=False, details=details)
    finally:
        cleanup_workspace(workspace_id)


def case_cross_thread_fact(client: RegressionClient) -> CaseResult:
    workspace = client.create_workspace("跨线程稳定事实回忆")
    workspace_id = UUID(workspace["id"])
    details: list[str] = [f"工作区: {workspace_id}"]
    try:
        client.chat(workspace_id=workspace_id, message="请记住：我们第一版部署方式是本地存储 + 本地 PostgreSQL + 可选 Redis。")
        answer = client.chat(workspace_id=workspace_id, message="我们第一版怎么部署？")

        _require(
            _contains_all(answer["answer"], ["本地存储", "PostgreSQL", "Redis"]),
            "跨线程事实回忆命中部署方式",
            details,
        )
        _require(
            _contains_none(answer["answer"], ["FastAPI", "React", "qwen3-max", "pgvector"]),
            "回答未混入无关背景",
            details,
        )
        return CaseResult(name="4. 跨线程稳定事实回忆", passed=True, details=details)
    except RegressionFailure as exc:
        details.append(f"异常: {exc}")
        return CaseResult(name="4. 跨线程稳定事实回忆", passed=False, details=details)
    finally:
        cleanup_workspace(workspace_id)


def case_episodic_memory(client: RegressionClient) -> CaseResult:
    workspace = client.create_workspace("情节记忆回忆")
    workspace_id = UUID(workspace["id"])
    details: list[str] = [f"工作区: {workspace_id}"]
    try:
        thread_id: UUID | None = None
        for message in (
            "这一轮我们新增了长期记忆系统。",
            "这一轮我们新增了背景信息压缩。",
            "这一轮我们新增了 Memory Center。",
        ):
            response = client.chat(workspace_id=workspace_id, thread_id=thread_id, message=message)
            thread_id = UUID(response["thread_id"])

        summary = client.chat(
            workspace_id=workspace_id,
            thread_id=thread_id,
            message="请总结一下我们这一轮新增的 3 个核心能力。",
        )
        recall = client.chat(workspace_id=workspace_id, message="上一轮我们新增的 3 个核心能力是什么？")
        episodic = client.list_memory(workspace_id=workspace_id, memory_type="episodic", query="核心能力")

        expected_terms = ["长期记忆", "背景信息压缩", "Memory Center"]
        _require(_contains_all(summary["answer"], expected_terms), "同线程事件总结命中 3 个核心能力", details)
        _require(_contains_all(recall["answer"], expected_terms), "跨线程事件回忆命中 3 个核心能力", details)
        _require(
            _contains_none(recall["answer"], ["FastAPI", "React", "qwen3-max", "pgvector"]),
            "情节回忆未混入无关项目背景",
            details,
        )
        _require(
            any(_contains_all(item.get("summary_text") or item.get("content_text", ""), expected_terms) for item in episodic),
            "事件总结已写入 episodic memory",
            details,
        )
        return CaseResult(name="5. 情节记忆回忆", passed=True, details=details)
    except RegressionFailure as exc:
        details.append(f"异常: {exc}")
        return CaseResult(name="5. 情节记忆回忆", passed=False, details=details)
    finally:
        cleanup_workspace(workspace_id)


def case_kb_overrides_memory(client: RegressionClient) -> CaseResult:
    workspace = client.create_workspace("知识库优先于错误记忆")
    workspace_id = UUID(workspace["id"])
    details: list[str] = [f"工作区: {workspace_id}"]
    try:
        uploaded = client.upload_document(workspace_id, KB_SAMPLE_PATH)
        document_id = UUID(uploaded["document_id"])
        client.chat(workspace_id=workspace_id, message="请记住：Business 套餐单文件大小上限是 500 MB。")
        answer = client.chat(
            workspace_id=workspace_id,
            message="Business 套餐的单文件大小上限是多少？",
            attachments=[document_id],
        )

        _require("200 MB" in answer["answer"], "知识库问答返回正确事实 200 MB", details)
        _require("500 MB" not in answer["answer"], "错误语义记忆未压过知识库证据", details)
        _require(len(answer["citations"]) >= 1, "知识库问答返回 citations", details)
        return CaseResult(name="6. 记忆不能覆盖知识库证据", passed=True, details=details)
    except RegressionFailure as exc:
        details.append(f"异常: {exc}")
        return CaseResult(name="6. 记忆不能覆盖知识库证据", passed=False, details=details)
    finally:
        cleanup_workspace(workspace_id)


def case_procedural_memory(client: RegressionClient) -> CaseResult:
    workspace = client.create_workspace("程序性记忆生效")
    workspace_id = UUID(workspace["id"])
    details: list[str] = [f"工作区: {workspace_id}"]
    try:
        uploaded = client.upload_document(workspace_id, KB_SAMPLE_PATH)
        document_id = UUID(uploaded["document_id"])
        client.create_memory(
            {
                "workspace_id": str(workspace_id),
                "memory_type": "procedural",
                "title": "知识库问答风格规则",
                "content_text": "回答知识库问题时，先给结论，再给 citations，不要展开无关背景。",
                "summary_text": "先结论，再给 citations，不展开无关背景。",
                "owner_user_id": str(settings.default_owner_user_id),
                "priority": 10,
                "metadata_json": {"source": "regression_suite"},
            }
        )
        answer = client.chat(
            workspace_id=workspace_id,
            message="Starter 套餐每个工作区最多可以连接多少个 MCP Server？",
            attachments=[document_id],
        )
        recalled_payload = _wait_for_recalled_memories(client, run_id=UUID(answer["run_id"]))

        _require("2" in answer["answer"], "程序性记忆场景下答案仍返回正确事实", details)
        _require(len(answer["citations"]) >= 1, "程序性记忆场景下仍返回 citations", details)
        _require(len(answer["answer"]) <= 120, "回答保持相对简洁", details)
        _require(
            len(recalled_payload) >= 1,
            "Trace 显示 procedural memory 已被召回",
            details,
        )
        return CaseResult(name="7. 程序性记忆生效", passed=True, details=details)
    except RegressionFailure as exc:
        details.append(f"异常: {exc}")
        return CaseResult(name="7. 程序性记忆生效", passed=False, details=details)
    finally:
        cleanup_workspace(workspace_id)


def main() -> int:
    client = RegressionClient()
    cases = [
        case_semantic_memory,
        case_combined_preferences,
        case_thread_summary,
        case_cross_thread_fact,
        case_episodic_memory,
        case_kb_overrides_memory,
        case_procedural_memory,
    ]
    results: list[CaseResult] = [case(client) for case in cases]

    print("记忆回归结果")
    print("=" * 60)
    failed = 0
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}")
        for detail in result.details:
            print(f"  - {detail}")
        print()
        if not result.passed:
            failed += 1

    print("=" * 60)
    print(f"总计: {len(results)} 组, 失败: {failed} 组")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
