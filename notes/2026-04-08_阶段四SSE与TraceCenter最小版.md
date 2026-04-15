# 2026-04-08 阶段四补充：SSE 与 Trace Center 最小版

## 本轮目标

- 增加流式聊天接口
- 增加 run 列表接口
- 在前端接入最小可用 Trace Center
- 让 Chat Workspace 可以直接跳转并查看当前 run 的 trace

## 已完成内容

### 1. 后端流式聊天接口

- 新增 `POST /api/chat/stream`
- 使用 `text/event-stream` 返回事件流
- 当前事件类型：
  - `run_created`
  - `step`
  - `final`
  - `done`
  - `error`
- 流式执行期间会分步提交数据库事务，使 step 和 snapshot 能在执行过程中落库

### 2. Run 列表接口

- 新增 `GET /api/runs?workspace_id=...&limit=...`
- 支持按 workspace 查看最近 run
- `RunRead` 现已包含：
  - `error_code`
  - `error_message`

### 3. ChatService 生命周期抽象

- 将聊天主流程拆为：
  - `prepare_chat(...)`
  - `complete_chat(...)`
  - `mark_run_failed(...)`
- 同步聊天和流式聊天复用同一套 run/thread/message 持久化逻辑

### 4. 前端 Streamed Chat

- `Chat Workspace` 现改为调用 `POST /api/chat/stream`
- 页面会实时显示：
  - 当前 `run_id`
  - 已完成的 graph step
  - 最终回答
  - citations
- 回答完成后可直接点击 `Open Current Trace` 或 `View Trace`

### 5. 前端 Trace Center 最小版

- `Trace Center` 现已接通：
  - 最近 run 列表
  - run summary
  - steps 列表
  - snapshots 列表
- 可切换 workspace 后查看对应 run
- 切 workspace 时会自动清理无效附件与无效 run 选择

## 关键文件

- `backend/app/api/routes/chat.py`
- `backend/app/api/routes/runs.py`
- `backend/app/repositories/run_repository.py`
- `backend/app/schemas/runs.py`
- `backend/app/services/chat/service.py`
- `frontend/src/App.tsx`
- `frontend/src/styles/index.css`

## 验证结果

### 自动化验证

- `python -m compileall backend/app backend/tests`
- `pytest backend/tests`
- `npm run build`

结果：

- 后端测试通过：`8 passed`
- 前端生产构建通过

### 真实链路 smoke test

通过 `TestClient` 调用：

- `POST /api/chat/stream`
- `GET /api/runs?workspace_id=...`
- `GET /api/runs/{run_id}/trace`

测试问题：

- `Business 套餐的单文件大小上限是多少？`

结果：

- Stream HTTP 状态：`200`
- SSE 事件总数：`8`
- 首个事件：`run_created`
- 最终事件：`done`
- `final.answer = 200 MB`
- `final.evidence_grade = sufficient`
- `runs` 列表返回正常
- `trace.steps = 9`
- `trace.snapshots = 9`

## 当前边界

- 现在的 SSE 是“节点级事件流”，不是 token 级输出
- `invoke_rag_subgraph` 在前端流里仍表现为聚合节点，子图内部节点主要在 Trace Center 中查看
- Trace Center 目前还是最小实现，尚未做筛选、搜索、时间轴和详情折叠

## 下一步建议

1. 将 `invoke_rag_subgraph` 的内部步骤进一步流式化
2. 增加真正的 token streaming 输出
3. 开始接入 Memory 节点
4. 再往后进入 Tool / MCP 编排阶段
