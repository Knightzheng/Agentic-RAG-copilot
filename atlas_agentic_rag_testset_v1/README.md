# Agentic RAG 测试知识库数据包（V1）

这个数据包用于你的 Agentic RAG 项目的本地联调、离线评测和前端演示。

## 文件说明

- `atlas_kb_test_corpus_v1.md`：合成知识库主文档
- `atlas_kb_test_qa_v1.json`：75 条单轮测试问题、标准答案、支撑章节
- `atlas_kb_test_conversations_v1.json`：8 组多轮对话测试样例
- `atlas_kb_test_eval_guide.md`：建议评测方式与判分口径

## 数据特点

- 单文档、强结构、规则明确，适合先验证最小可用 RAG
- 含单跳、多跳、版本变更、条件例外、数值计算、证据不足、追问上下文
- 支持测试：
  - 文档接入与切分
  - Hybrid Retrieval
  - Rerank
  - 引用绑定
  - 多轮追问
  - 审批/策略类问答
  - “证据不足”保守回答

## 推荐用法

### 第一阶段：最小 RAG
1. 上传 `atlas_kb_test_corpus_v1.md`
2. 导入 `atlas_kb_test_qa_v1.json`
3. 先跑 15 条 easy + 15 条 medium
4. 检查 Recall@5、答案准确率、引用准确率

### 第二阶段：Agentic 能力
1. 跑 `multi_hop`、`policy`、`follow_up_ready`
2. 再跑 `atlas_kb_test_conversations_v1.json`
3. 检查：
   - query rewrite
   - thread context 利用
   - 规则冲突时是否优先新版规则
   - 证据不足题是否拒答或保守回答

### 第三阶段：评测看板
建议至少统计：
- Retrieval Recall@5
- Citation Precision
- Answer Accuracy
- Faithfulness
- Insufficient Detection Accuracy

## 数据规模

- 单轮 QA：75 条
- 多轮对话：8 组
