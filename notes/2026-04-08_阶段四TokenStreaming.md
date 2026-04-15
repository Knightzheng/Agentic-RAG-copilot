# 2026-04-08 阶段四补充：Token Streaming

## 本轮目标

- 为 `rag.generate_grounded_answer` 增加真正的 token 级增量输出
- 保持节点级 SSE、Trace 落库和同步 `/api/chat` 能力不回归
- 让前端在回答生成阶段实时看到答案草稿

## 已完成内容

### 1. DashScope 流式客户端

- `DashScopeClient` 新增 `chat_stream(...)`
- 通过 OpenAI-compatible `chat/completions` 流式接口消费 SSE
- 当前会解析：
  - `delta`
  - `usage`
  - `finish`
  - `done`

### 2. 图编排内的 answer token 回调

- `AtlasSupervisorGraphService` 新增 `set_answer_token_callback(...)`
- direct 路由支持直接流式输出文本
- `rag.generate_grounded_answer` 在流式模式下：
  - 继续要求模型输出 JSON
  - 增量解析 JSON 中的 `answer` 字段
  - 仅把 `answer` 文本增量推给前端
- 这样既能保留最终 `citations` 解析，又能让前端看到自然语言答案流

### 3. 后端流式执行模型

- `POST /api/chat/stream` 已改为：
  - 后台线程执行图编排
  - 主线程通过事件队列持续返回 SSE
- 当前可混合输出：
  - `run_created`
  - `step`
  - `token`
  - `final`
  - `done`
  - `error`

### 4. 前端实时答案草稿

- `Chat Workspace` 增加 `Live Answer Draft`
- 收到 `token` 事件时会实时追加答案
- 收到 `final` 事件时会同步为最终答案

### 5. 新增单测

- 增加 `_extract_partial_answer_text(...)` 的回归测试
- 当前编排相关测试已覆盖：
  - 路由分类
  - citation payload 映射
  - trace 摘要
  - 精确问答压缩
  - 流式 JSON answer 提取

## 关键文件

- `backend/app/services/llm/dashscope_client.py`
- `backend/app/services/orchestration/graph.py`
- `backend/app/api/routes/chat.py`
- `frontend/src/App.tsx`
- `frontend/src/styles/index.css`
- `backend/tests/test_orchestration_trace.py`

## 验证结果

### 自动化验证

- `python -m compileall backend/app backend/tests`
- `pytest backend/tests`
- `npm run build`

结果：

- 后端测试通过：`9 passed`
- 前端生产构建通过

### 真实链路 smoke test

测试问题：

- `Business 套餐的单文件大小上限是多少？`

结果：

- `POST /api/chat`：`answer = 200 MB`
- `POST /api/chat/stream`：
  - HTTP 状态 `200`
  - 事件序列包含 `token`
  - `token_count = 2`
  - 最终 `final.answer = 200 MB`
  - `final.evidence_grade = sufficient`
- `GET /api/runs/{run_id}/trace`：
  - `trace.steps = 9`
  - `trace.snapshots = 9`

## 当前边界

- 当前 token streaming 只覆盖回答生成阶段，不覆盖检索阶段
- 流式草稿可能与最终压缩后的答案略有差异，但最终 `final` 事件会收敛到最终答案
- 目前还没有 token 级取消、中断或重试能力

## 下一步建议

1. 增加前端“停止生成”能力
2. 给流式路由补取消信号和中断清理
3. 再往后进入 Memory 节点和多轮状态编排
