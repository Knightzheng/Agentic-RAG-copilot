# 2026-04-08 阶段四：LangGraph 编排与 Trace 基础

## 本阶段目标

- 将现有同步 RAG 问答链路切换为 LangGraph 编排
- 增加节点级执行记录与状态快照
- 保持现有 `/api/chat` 返回结构不变
- 为后续 SSE、Trace Center 页面和 Tool/MCP 编排打基础

## 已完成内容

### 1. LangGraph 最小主图与 RAG 子图

- 新增 `AtlasAgentState`，作为当前 Milestone 4 的最小运行时状态
- 新增 `AtlasSupervisorGraphService`
- 主图节点：
  - `load_thread_context`
  - `classify_request`
  - `invoke_rag_subgraph`
  - `invoke_direct_answer`
  - `compose_final_answer`
  - `finish`
- RAG 子图节点：
  - `rag.normalize_query`
  - `rag.retrieve_candidates`
  - `rag.grade_evidence`
  - `rag.generate_grounded_answer`

### 2. Run Step / Snapshot Trace

- 新增表：
  - `app_agent.agent_run_steps`
  - `app_agent.run_state_snapshots`
- 新增 `RunTraceRecorder`，在图节点执行时自动记录：
  - 输入摘要
  - 输出摘要
  - 错误信息
  - step 级状态
  - 节点完成后的状态快照

### 3. Chat 入口切换到图执行

- `ChatService` 不再直接串行调用 retrieval + answer
- 当前流程改为：
  - 创建 thread / user message / agent run
  - 构造 graph state
  - 调用 `AtlasSupervisorGraphService.invoke(...)`
  - 回写 assistant message / citation / evidence assessment / run summary
- 失败执行时会把 `run.status = failed` 等状态先写回，再抛出错误

### 4. Trace API

- 新增：
  - `GET /api/runs/{run_id}`
  - `GET /api/runs/{run_id}/steps`
  - `GET /api/runs/{run_id}/trace`

### 5. 回答质量防回归

- 在 grounded answer 阶段增加“简单事实题压缩”逻辑
- 当问题属于精确属性问答且模型输出被扩写成整段说明时，会优先压缩回证据行
- 该逻辑用于保护第三阶段已经修好的精确问答质量

## 关键文件

- `backend/app/services/orchestration/state.py`
- `backend/app/services/orchestration/tracing.py`
- `backend/app/services/orchestration/graph.py`
- `backend/app/services/chat/service.py`
- `backend/app/api/routes/chat.py`
- `backend/app/api/routes/runs.py`
- `backend/app/repositories/run_repository.py`
- `backend/app/schemas/runs.py`
- `backend/app/models/agent.py`
- `backend/alembic/versions/20260408_0003_langgraph_trace.py`
- `backend/tests/test_orchestration_trace.py`

## 验证结果

### 依赖与迁移

- 已安装 `langgraph`
- Alembic 已升级到 `20260408_0003`

### 自动化验证

- `python -m compileall backend/app backend/tests`
- `pytest backend/tests`
- 结果：`8 passed`

### 真实链路 smoke test

使用 `Atlas Demo Workspace` 与测试知识库文档执行问题：

- 问题：`Business 套餐的单文件大小上限是多少？`

结果：

- `status = completed`
- `evidence_grade = sufficient`
- `answer = 200 MB`
- `citations = 1`
- `steps = 9`
- `snapshots = 9`

## 当前边界

- 还没有做 SSE 流式输出
- 还没有做前端 Trace Center 页面
- 还没有做 LangGraph persistence / checkpoint 恢复
- 还没有接入 Memory、Tool、MCP
- direct 路由目前只是最小 fallback，还不是完整 agent 模式

## 下一步建议

1. 进入 Trace Center 前端最小页，把 `/runs/{id}/trace` 接出来
2. 增加 `/api/chat/stream`，让图执行支持 SSE 输出
3. 再往后接 Memory 节点与 Tool/MCP 节点，逐步把主图扩成真正的 Agent 流程
