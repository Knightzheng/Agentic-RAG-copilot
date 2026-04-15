export type Locale = "zh" | "en";

export const PAGE_KEYS = ["chat", "kb", "trace", "memory", "mcp"] as const;
export type PageKey = (typeof PAGE_KEYS)[number];

type StepCopy = {
  label: string;
  typeLabel?: string;
  running: string;
  completed?: string;
};

export const PAGE_COPY: Record<Locale, Record<PageKey, { label: string; description: string }>> = {
  zh: {
    chat: { label: "对话工作台", description: "基于 SSE 的 RAG 对话，可查看引用和实时图执行进度。" },
    kb: { label: "知识库", description: "上传、解析、切块、向量化并重建本地知识文档索引。" },
    trace: { label: "追踪中心", description: "查看最近运行、步骤级执行过程与图状态快照。" },
    memory: { label: "记忆中心", description: "管理语义记忆、情节记忆和程序性记忆，并供后续召回使用。" },
    mcp: { label: "MCP 中心", description: "预留给下一阶段功能。" },
  },
  en: {
    chat: { label: "Chat Workspace", description: "SSE streamed RAG chat with citations and live graph progress." },
    kb: { label: "Knowledge Base", description: "Upload, parse, chunk, embed, and reindex local knowledge documents." },
    trace: { label: "Trace Center", description: "Inspect recent runs, step-level execution, and graph state snapshots." },
    memory: { label: "Memory Center", description: "Manage semantic, episodic, and procedural memory with recall-ready records." },
    mcp: { label: "MCP Hub", description: "Reserved for the next milestone." },
  },
};

export const STEP_COPY: Record<Locale, Record<string, StepCopy>> = {
  zh: {
    load_thread_context: {
      label: "加载线程上下文",
      typeLabel: "上下文",
      running: "正在加载历史消息和已固定文档。",
      completed: "线程上下文已就绪。",
    },
    classify_request: {
      label: "识别请求类型",
      typeLabel: "路由",
      running: "正在判断当前请求应该走直接问答还是 RAG。",
      completed: "请求路由判断完成。",
    },
    recall_long_term_memory: {
      label: "召回长期记忆",
      typeLabel: "记忆",
      running: "正在检索相关的语义记忆、情节记忆和程序性记忆。",
      completed: "长期记忆召回完成。",
    },
    invoke_rag_subgraph: {
      label: "进入 RAG 子图",
      typeLabel: "子图",
      running: "正在切换到 RAG 执行链路。",
      completed: "RAG 子图已激活。",
    },
    "rag.rewrite_follow_up": {
      label: "改写追问",
      typeLabel: "RAG",
      running: "正在判断最新问题是否依赖前文上下文。",
      completed: "追问改写完成。",
    },
    "rag.normalize_query": {
      label: "规范检索问题",
      typeLabel: "RAG",
      running: "正在清洗并规范检索查询。",
      completed: "检索问题规范化完成。",
    },
    "rag.retrieve_candidates": {
      label: "检索候选片段",
      typeLabel: "RAG",
      running: "正在从知识库中检索相关片段。",
      completed: "候选片段检索完成。",
    },
    "rag.grade_evidence": {
      label: "评估证据强度",
      typeLabel: "RAG",
      running: "正在判断检索证据的充分性。",
      completed: "证据强度评估完成。",
    },
    "rag.generate_grounded_answer": {
      label: "生成受约束回答",
      typeLabel: "生成",
      running: "正在依据检索证据生成回答。",
      completed: "受约束回答已生成。",
    },
    invoke_direct_answer: {
      label: "直接回答",
      typeLabel: "生成",
      running: "正在不经检索直接生成回答。",
      completed: "直接回答已生成。",
    },
    compose_final_answer: {
      label: "组装最终回答",
      typeLabel: "响应",
      running: "正在整理最终回答、引用与证据结论。",
      completed: "最终响应载荷已准备完成。",
    },
    finish: {
      label: "结束运行",
      typeLabel: "收尾",
      running: "正在结束本次图执行并持久化结果。",
      completed: "运行已完成并落库。",
    },
  },
  en: {
    load_thread_context: {
      label: "Load Thread Context",
      typeLabel: "Context",
      running: "Loading prior messages and pinned documents.",
      completed: "Thread context is ready.",
    },
    classify_request: {
      label: "Classify Request",
      typeLabel: "Routing",
      running: "Deciding whether the request should use direct chat or RAG.",
      completed: "Route decision completed.",
    },
    recall_long_term_memory: {
      label: "Recall Long-Term Memory",
      typeLabel: "Memory",
      running: "Searching semantic, episodic, and procedural memory for relevant context.",
      completed: "Relevant long-term memories have been recalled.",
    },
    invoke_rag_subgraph: {
      label: "Enter RAG Pipeline",
      typeLabel: "Subgraph",
      running: "Switching execution into the RAG pipeline.",
      completed: "RAG pipeline activated.",
    },
    "rag.rewrite_follow_up": {
      label: "Rewrite Follow-Up",
      typeLabel: "RAG",
      running: "Resolving whether the latest question depends on earlier thread context.",
      completed: "Follow-up query rewrite completed.",
    },
    "rag.normalize_query": {
      label: "Normalize Query",
      typeLabel: "RAG",
      running: "Cleaning and normalizing the retrieval query.",
      completed: "Query normalization completed.",
    },
    "rag.retrieve_candidates": {
      label: "Retrieve Candidates",
      typeLabel: "RAG",
      running: "Searching the knowledge base for relevant chunks.",
      completed: "Candidate retrieval completed.",
    },
    "rag.grade_evidence": {
      label: "Grade Evidence",
      typeLabel: "RAG",
      running: "Assessing how strong the retrieved evidence is.",
      completed: "Evidence strength has been graded.",
    },
    "rag.generate_grounded_answer": {
      label: "Generate Grounded Answer",
      typeLabel: "Generation",
      running: "Drafting an answer constrained by retrieved evidence.",
      completed: "Grounded answer generated.",
    },
    invoke_direct_answer: {
      label: "Generate Direct Answer",
      typeLabel: "Generation",
      running: "Generating a direct answer without retrieval.",
      completed: "Direct answer generated.",
    },
    compose_final_answer: {
      label: "Compose Final Answer",
      typeLabel: "Response",
      running: "Finalizing answer text, citations, and evidence result.",
      completed: "Final answer payload prepared.",
    },
    finish: {
      label: "Finish Run",
      typeLabel: "Finalize",
      running: "Closing the graph run and persisting the outcome.",
      completed: "Run completed and persisted.",
    },
  },
};

export const UI_TEXT = {
  zh: {
    brandSubtitle: "智能体 RAG 副驾驶",
    createDefaultWorkspace: "创建默认工作区",
    creating: "创建中...",
    language: "语言",
    switchToEnglish: "EN",
    switchToChinese: "中文",
    workspaces: "工作区",
    threads: "线程",
    runs: "运行",
    documentUpload: "文档上传",
    documentUploadDesc: "支持 PDF、DOCX、PPTX、MD 和 TXT，上传后会自动触发解析、切块和索引。",
    uploadAndParse: "上传并解析",
    uploading: "上传中...",
    knowledgeBase: "知识库",
    knowledgeBaseDesc: "当前本地文档集合及其解析、索引状态。",
    noDocuments: "当前还没有文档。请先创建或选择工作区，再上传样例文件。",
    reindex: "重建索引",
    reindexing: "重建中...",
    threadListTitle: "线程列表",
    threadListDesc: "当前工作区下保存的对话线程。",
    newThread: "新建线程",
    noThreads: "当前还没有线程。你的第一条问题会自动创建线程。",
    streamChatTitle: "流式对话",
    streamChatDesc: "调用 POST /api/chat/stream，并实时展示图执行进度。",
    chatPlaceholder: "示例：Business 套餐的单文件大小上限是多少？",
    sendQuestion: "发送问题",
    streaming: "流式生成中...",
    stop: "停止",
    retryLastRun: "重试上一次运行",
    openCurrentTrace: "打开当前 Trace",
    currentThread: "当前线程",
    loading: "加载中...",
    loadingThreadHistory: "正在加载线程历史...",
    compressedBackground: "压缩背景",
    threadHistoryUnavailable: "当前无法获取线程历史。",
    noThreadSelected: "尚未选择线程。现在发送问题会自动创建新线程。",
    liveAnswerDraft: "实时回答草稿",
    liveGraphProgress: "实时图执行进度",
    inProgress: "进行中",
    answersAppearHere: "当前会话的回答和引用会显示在这里。",
    regenerate: "重新生成",
    viewTrace: "查看 Trace",
    questionPrefix: "问：",
    answerPrefix: "答：",
    evidencePrefix: "证据：",
    recentRuns: "最近运行",
    recentRunsDesc: "所选工作区最近的图执行记录。",
    noRuns: "当前还没有运行记录。请先发起一次提问。",
    runTrace: "运行 Trace",
    runTraceDesc: "查看所选运行的步骤记录和压缩状态。",
    retrySelectedRun: "重试当前运行",
    loadingTrace: "正在加载 Trace...",
    status: "状态",
    route: "路由",
    evidence: "证据",
    steps: "步骤",
    snapshots: "快照",
    selectRun: "请选择一条运行记录查看详情。",
    memoryInventory: "记忆清单",
    memoryInventoryDesc: "查看和检索当前工作区的语义记忆、情节记忆和程序性记忆。",
    refresh: "刷新",
    allTypes: "全部类型",
    semantic: "语义记忆",
    episodic: "情节记忆",
    procedural: "程序性记忆",
    searchTitleOrContent: "搜索标题或内容",
    pinnedOnly: "仅看已固定",
    applyFilters: "应用筛选",
    noMemories: "当前还没有记忆记录。可以手动创建，也可以让聊天自动写入。",
    pinned: "已固定",
    score: "分数",
    pin: "固定",
    unpin: "取消固定",
    sourceRun: "来源运行",
    delete: "删除",
    editMemory: "编辑记忆",
    createMemory: "创建记忆",
    memoryFormDesc: "程序性记忆适合存规则，语义记忆适合存事实与偏好。",
    newRecord: "新建记录",
    memoryType: "记忆类型",
    priority: "优先级",
    title: "标题",
    summary: "摘要",
    summaryPlaceholder: "可选，用于快速查看的简短摘要。",
    content: "正文",
    contentPlaceholder: "在这里填写完整记忆内容。",
    metadataJson: "元数据 JSON",
    saveChanges: "保存修改",
    reloadSelected: "重新加载当前记录",
    reservedDesc: "该页面预留给下一阶段功能。",
    runStatus: "运行状态",
    modePrefix: "模式",
    active: "当前",
    userLabel: "用户",
    assistantLabel: "助手",
    metadataJsonInvalid: "Metadata 必须是合法 JSON。",
    memoryUpdated: "记忆已更新。",
    memoryCreated: "记忆已创建。",
    memorySaveFailed: "保存记忆失败",
    memoryPinned: "记忆已固定。",
    memoryUnpinned: "记忆已取消固定。",
    pinUpdateFailed: "更新固定状态失败",
    memoryDeleted: "记忆已删除。",
    deleteFailed: "删除失败",
    uploadFailed: "上传失败",
    uploadFinished: "上传完成，当前状态：{status}",
    duplicateDetected: "检测到重复文档，已复用现有文档：{documentId}",
    generationStopped: "生成已停止。",
    chatFailed: "聊天失败",
    stopFailed: "停止失败",
    stoppingGeneration: "正在停止生成...",
    runStatusLine: "运行状态：{status}",
    reindexFinished: "重建索引完成，当前状态：{status}",
    reindexFailed: "重建索引失败",
    memoryLoadFailed: "记忆加载失败",
    createDefaultWorkspaceName: "Atlas 演示工作区",
    retryOfRun: "运行 {runId} 的重试",
  },
  en: {
    brandSubtitle: "Agentic RAG Copilot",
    createDefaultWorkspace: "Create Default Workspace",
    creating: "Creating...",
    language: "Language",
    switchToEnglish: "EN",
    switchToChinese: "中文",
    workspaces: "Workspaces",
    threads: "Threads",
    runs: "Runs",
    documentUpload: "Document Upload",
    documentUploadDesc: "Supports PDF, DOCX, PPTX, MD, and TXT. Upload triggers parse, chunking, and indexing.",
    uploadAndParse: "Upload and Parse",
    uploading: "Uploading...",
    knowledgeBase: "Knowledge Base",
    knowledgeBaseDesc: "Current local document set with parser and index status.",
    noDocuments: "No documents yet. Create or select a workspace and upload a sample file.",
    reindex: "Reindex",
    reindexing: "Reindexing...",
    threadListTitle: "Threads",
    threadListDesc: "Stored conversation threads for the current workspace.",
    newThread: "New Thread",
    noThreads: "No threads yet. Your first question will create one automatically.",
    streamChatTitle: "Streamed Chat",
    streamChatDesc: "Calls POST /api/chat/stream and shows graph progress in real time.",
    chatPlaceholder: "Example: What is the single-file size limit for the Business plan?",
    sendQuestion: "Send Question",
    streaming: "Streaming...",
    stop: "Stop",
    retryLastRun: "Retry Last Run",
    openCurrentTrace: "Open Current Trace",
    currentThread: "Current Thread",
    loading: "Loading...",
    loadingThreadHistory: "Loading thread history...",
    compressedBackground: "Compressed Background",
    threadHistoryUnavailable: "Thread history is unavailable.",
    noThreadSelected: "No thread selected. Sending a question now will create a new thread.",
    liveAnswerDraft: "Live Answer Draft",
    liveGraphProgress: "Live Graph Progress",
    inProgress: "in progress",
    answersAppearHere: "Answers and citations from this session will appear here.",
    regenerate: "Regenerate",
    viewTrace: "View Trace",
    questionPrefix: "Q:",
    answerPrefix: "A:",
    evidencePrefix: "evidence=",
    recentRuns: "Recent Runs",
    recentRunsDesc: "Most recent graph executions for the selected workspace.",
    noRuns: "No runs yet. Ask a question first.",
    runTrace: "Run Trace",
    runTraceDesc: "Step records and condensed graph state for the selected run.",
    retrySelectedRun: "Retry Selected Run",
    loadingTrace: "Loading trace...",
    status: "Status",
    route: "Route",
    evidence: "Evidence",
    steps: "Steps",
    snapshots: "Snapshots",
    selectRun: "Select a run to inspect its trace.",
    memoryInventory: "Memory Inventory",
    memoryInventoryDesc: "Search and review semantic, episodic, and procedural memory records for the current workspace.",
    refresh: "Refresh",
    allTypes: "All Types",
    semantic: "Semantic",
    episodic: "Episodic",
    procedural: "Procedural",
    searchTitleOrContent: "Search title or content",
    pinnedOnly: "Pinned only",
    applyFilters: "Apply Filters",
    noMemories: "No memory records yet. Create one or let chat turns write memory automatically.",
    pinned: "pinned",
    score: "score",
    pin: "Pin",
    unpin: "Unpin",
    sourceRun: "Source Run",
    delete: "Delete",
    editMemory: "Edit Memory",
    createMemory: "Create Memory",
    memoryFormDesc: "Procedural memories are best for reusable rules. Semantic memories store facts or preferences.",
    newRecord: "New Record",
    memoryType: "Memory Type",
    priority: "Priority",
    title: "Title",
    summary: "Summary",
    summaryPlaceholder: "Optional compact summary used for quick inspection.",
    content: "Content",
    contentPlaceholder: "Store the full memory content here.",
    metadataJson: "Metadata JSON",
    saveChanges: "Save Changes",
    reloadSelected: "Reload Selected",
    reservedDesc: "This page stays reserved for the next milestone.",
    runStatus: "Run Status",
    modePrefix: "mode",
    active: "active",
    userLabel: "User",
    assistantLabel: "Assistant",
    metadataJsonInvalid: "Metadata must be valid JSON.",
    memoryUpdated: "Memory updated.",
    memoryCreated: "Memory created.",
    memorySaveFailed: "Memory save failed",
    memoryPinned: "Memory pinned.",
    memoryUnpinned: "Memory unpinned.",
    pinUpdateFailed: "Pin update failed",
    memoryDeleted: "Memory deleted.",
    deleteFailed: "Delete failed",
    uploadFailed: "Upload failed",
    uploadFinished: "Upload finished. Current status: {status}",
    duplicateDetected: "Duplicate detected. Reused existing document: {documentId}",
    generationStopped: "Generation stopped.",
    chatFailed: "Chat failed",
    stopFailed: "Stop failed",
    stoppingGeneration: "Stopping generation...",
    runStatusLine: "Run status: {status}",
    reindexFinished: "Reindex finished. Current status: {status}",
    reindexFailed: "Reindex failed",
    memoryLoadFailed: "Memory load failed",
    createDefaultWorkspaceName: "Atlas Demo Workspace",
    retryOfRun: "Retry of run {runId}",
  },
} as const;

export function fillTemplate(template: string, params: Record<string, string | number>): string {
  return Object.entries(params).reduce(
    (result, [key, value]) => result.split(`{${key}}`).join(String(value)),
    template,
  );
}

export function formatMode(locale: Locale, mode: string): string {
  const map: Record<string, string> =
    locale === "zh"
      ? { auto: "自动", direct: "直接问答", rag: "RAG", hybrid: "混合" }
      : { auto: "auto", direct: "direct", rag: "rag", hybrid: "hybrid" };
  return map[mode] ?? mode;
}

export function formatStatus(locale: Locale, status: string): string {
  const map: Record<string, string> =
    locale === "zh"
      ? {
          running: "运行中",
          completed: "已完成",
          cancelled: "已取消",
          failed: "失败",
          active: "活跃",
          success: "成功",
          sufficient: "充分",
          weak: "较弱",
          insufficient: "不足",
          processing: "处理中",
          ready: "就绪",
        }
      : {
          running: "Running",
          completed: "Completed",
          cancelled: "Cancelled",
          failed: "Failed",
          active: "active",
          success: "success",
          sufficient: "sufficient",
          weak: "weak",
          insufficient: "insufficient",
          processing: "processing",
          ready: "ready",
        };
  return map[status] ?? status;
}

export function formatRequestType(locale: Locale, requestType: string): string {
  const map: Record<string, string> =
    locale === "zh"
      ? {
          kb_qa: "知识库问答",
          smalltalk: "普通对话",
          memory: "记忆读写",
          thread_context: "线程背景",
          context_update: "背景更新",
          event_memory: "事件回忆",
        }
      : {
          kb_qa: "KB QA",
          smalltalk: "Smalltalk",
          memory: "Memory",
          thread_context: "Thread Context",
          context_update: "Context Update",
          event_memory: "Event Memory",
        };
  return map[requestType] ?? requestType;
}

export function formatRoute(locale: Locale, route: string): string {
  const map: Record<string, string> =
    locale === "zh"
      ? { rag: "RAG", direct: "直接问答", hybrid: "混合" }
      : { rag: "RAG", direct: "Direct", hybrid: "Hybrid" };
  return map[route] ?? route;
}

export function formatMemoryType(locale: Locale, memoryType: string): string {
  const map: Record<string, string> =
    locale === "zh"
      ? { semantic: "语义记忆", episodic: "情节记忆", procedural: "程序性记忆" }
      : { semantic: "Semantic", episodic: "Episodic", procedural: "Procedural" };
  return map[memoryType] ?? memoryType;
}

export function formatStepStatus(locale: Locale, status: string): string {
  return formatStatus(locale, status);
}

export function getStepLabel(locale: Locale, stepKey: string): string {
  return STEP_COPY[locale][stepKey]?.label ?? stepKey;
}

export function getStepTypeLabel(locale: Locale, stepKey: string, stepType: string): string {
  if (STEP_COPY[locale][stepKey]?.typeLabel) {
    return STEP_COPY[locale][stepKey].typeLabel!;
  }
  if (locale === "zh") {
    if (stepType === "rag_node") return "RAG";
    if (stepType === "subgraph") return "子图";
    if (stepType === "graph_node") return "图节点";
  } else {
    if (stepType === "rag_node") return "RAG";
    if (stepType === "subgraph") return "Subgraph";
    if (stepType === "graph_node") return "Graph";
  }
  return stepType;
}

export function getStepNarrative(
  locale: Locale,
  stepKey: string,
  status: string,
  preview: string,
  errorMessage?: string,
): string {
  if (status === "failed") {
    return errorMessage || (locale === "zh" ? "该步骤执行失败。" : "The step failed.");
  }
  if (status === "cancelled") {
    return errorMessage || (locale === "zh" ? "该步骤已取消。" : "The step was cancelled.");
  }
  if (preview) {
    return preview;
  }
  const copy = STEP_COPY[locale][stepKey];
  if (!copy) {
    return "";
  }
  if (status === "completed" && copy.completed) {
    return copy.completed;
  }
  return copy.running;
}

export function summarizeOutput(locale: Locale, value: unknown): string {
  const ui = UI_TEXT[locale];
  if (!value || typeof value !== "object") {
    return typeof value === "string" ? value : "";
  }

  const output = value as Record<string, unknown>;
  if (typeof output.normalized_message === "string" && output.normalized_message) {
    return locale === "zh" ? `查询=${output.normalized_message}` : `query=${output.normalized_message}`;
  }
  if (Array.isArray(output.recalled_memories)) {
    return locale === "zh" ? `记忆=${output.recalled_memories.length}` : `memories=${output.recalled_memories.length}`;
  }
  if (typeof output.thread_summary === "string" && output.thread_summary) {
    return locale === "zh" ? "线程摘要已加载" : "thread summary loaded";
  }
  if (Array.isArray(output.retrieved_candidates)) {
    return locale === "zh" ? `检索结果=${output.retrieved_candidates.length}` : `retrieved=${output.retrieved_candidates.length}`;
  }
  if (typeof output.final_answer === "string" && output.final_answer) {
    return output.final_answer.slice(0, 120);
  }
  if (typeof output.evidence_grade === "string" && output.evidence_grade) {
    return `${ui.evidencePrefix}${formatStatus(locale, output.evidence_grade)}`;
  }
  if (typeof output.insufficiency_reason === "string" && output.insufficiency_reason) {
    return output.insufficiency_reason;
  }
  if (Array.isArray(output.citation_candidates)) {
    return locale === "zh" ? `引用=${output.citation_candidates.length}` : `citations=${output.citation_candidates.length}`;
  }
  if (output.metrics && typeof output.metrics === "object" && "candidate_count" in output.metrics) {
    const metrics = output.metrics as Record<string, unknown>;
    return locale === "zh"
      ? `候选=${String(metrics.candidate_count ?? "-")}`
      : `candidates=${String(metrics.candidate_count ?? "-")}`;
  }
  if (typeof output.status === "string") {
    return formatStatus(locale, output.status);
  }
  return JSON.stringify(output).slice(0, 120);
}
