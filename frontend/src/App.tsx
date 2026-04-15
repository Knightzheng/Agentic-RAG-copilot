import { useEffect, useState } from "react";

import {
  PAGE_COPY,
  PAGE_KEYS,
  STEP_COPY,
  UI_TEXT,
  type Locale,
  type PageKey,
  fillTemplate,
  formatMemoryType,
  formatMode,
  formatRequestType,
  formatRoute,
  formatStatus,
  formatStepStatus,
  getStepLabel,
  getStepNarrative,
  getStepTypeLabel,
  summarizeOutput,
} from "./i18n";

type Workspace = {
  id: string;
  name: string;
  slug: string;
};

type Thread = {
  id: string;
  title: string;
  mode: string;
  status: string;
};

type ThreadMessage = {
  id: string;
  role: string;
  content_text: string;
  sequence_no: number;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

type ThreadDetail = {
  id: string;
  workspace_id: string;
  title: string;
  mode: string;
  status: string;
  thread_summary?: string | null;
  messages: ThreadMessage[];
};

type DocumentRecord = {
  id: string;
  title: string;
  original_filename: string;
  file_type: string;
  status: string;
};

type Citation = {
  chunk_id: string;
  document_id: string;
  citation_label: string;
  section_path: string[];
  snippet: string;
};

type ChatTurn = {
  runId: string;
  threadId: string;
  question: string;
  answer: string;
  evidenceGrade: string;
  citations: Citation[];
};

type RunSummary = {
  id: string;
  thread_id: string;
  workspace_id: string;
  user_id: string;
  request_type: string;
  route_target: string;
  status: string;
  result_status: string | null;
  evidence_grade: string | null;
  error_code: string | null;
  error_message: string | null;
  token_usage_json: Record<string, unknown>;
  metrics_json: Record<string, unknown>;
  started_at: string;
  ended_at: string | null;
  created_at: string;
};

type RunStep = {
  id: string;
  run_id: string;
  thread_id: string;
  step_key: string;
  step_type: string;
  status: string;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  ended_at: string | null;
  created_at: string;
};

type RunSnapshot = {
  id: string;
  run_id: string;
  thread_id: string;
  step_key: string;
  snapshot_index: number;
  state_json: Record<string, unknown>;
  created_at: string;
};

type RunTrace = {
  run: RunSummary;
  steps: RunStep[];
  snapshots: RunSnapshot[];
};

type MemoryRecord = {
  id: string;
  workspace_id: string;
  memory_type: string;
  title: string;
  content_text: string;
  summary_text: string | null;
  source_run_id: string | null;
  source_thread_id: string | null;
  owner_user_id: string | null;
  priority: number | null;
  confidence_score: number | null;
  score: number | null;
  is_pinned: boolean;
  is_active: boolean;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type StreamStep = {
  stepKey: string;
  stepType: string;
  status: string;
  preview: string;
  startedAt: string;
  endedAt?: string | null;
  durationMs?: number | null;
  errorMessage?: string;
};

type StreamEvent =
  | {
      event: "run_created";
      data: {
        run_id: string;
        thread_id: string;
        status: string;
        question?: string;
        retry_of_run_id?: string | null;
      };
    }
  | {
      event: "step";
      data: {
        run_id: string;
        thread_id: string;
        step_key: string;
        step_type: string;
        status: string;
        started_at: string;
        ended_at?: string | null;
        duration_ms?: number | null;
        output: unknown;
        error?: { type?: string; message?: string } | null;
      };
    }
  | { event: "token"; data: { run_id: string; thread_id: string; delta: string; answer: string } }
  | {
      event: "cancelled";
      data: {
        run_id: string;
        thread_id: string;
        status: string;
        answer: string;
        question?: string;
        retry_of_run_id?: string | null;
      };
    }
  | {
      event: "final";
      data: {
        run_id: string;
        thread_id: string;
        status: string;
        answer: string;
        evidence_grade: string;
        citations: Citation[];
        question?: string;
        retry_of_run_id?: string | null;
      };
    }
  | { event: "done"; data: { run_id: string; thread_id: string; status: string } }
  | { event: "error"; data: { type: string; message: string; run_id?: string; thread_id?: string } };

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";
const OWNER_USER_ID = "00000000-0000-0000-0000-000000000001";

function buildQueryString(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    search.set(key, String(value));
  });
  const serialized = search.toString();
  return serialized ? `?${serialized}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

async function streamRequest(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Stream request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    buffer = buffer.replace(/\r\n/g, "\n");

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const chunk = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      const event = parseSseChunk(chunk);
      if (event) {
        onEvent(event);
      }
      boundary = buffer.indexOf("\n\n");
    }

    if (done) {
      const tail = buffer.trim();
      if (tail) {
        const event = parseSseChunk(tail);
        if (event) {
          onEvent(event);
        }
      }
      break;
    }
  }
}

function parseSseChunk(chunk: string): StreamEvent | null {
  if (!chunk) {
    return null;
  }

  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    event: eventName,
    data: JSON.parse(dataLines.join("\n")),
  } as StreamEvent;
}

function formatDate(locale: Locale, value: string | null): string {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString(locale === "zh" ? "zh-CN" : "en-US");
}

function formatDuration(durationMs: number | null | undefined): string {
  if (durationMs == null || Number.isNaN(durationMs)) {
    return "-";
  }
  if (durationMs < 1000) {
    return `${durationMs} ms`;
  }
  return `${(durationMs / 1000).toFixed(durationMs >= 10_000 ? 0 : 1)} s`;
}

function getDurationFromTimestamps(startedAt: string, endedAt: string | null): number | null {
  if (!startedAt || !endedAt) {
    return null;
  }
  const start = new Date(startedAt).getTime();
  const end = new Date(endedAt).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) {
    return null;
  }
  return Math.max(0, end - start);
}

function upsertStreamStep(current: StreamStep[], nextStep: StreamStep): StreamStep[] {
  const existingIndex = current.findIndex((item) => item.stepKey === nextStep.stepKey);
  if (existingIndex === -1) {
    return [...current, nextStep];
  }

  const updated = [...current];
  updated[existingIndex] = {
    ...updated[existingIndex],
    ...nextStep,
  };
  return updated;
}

export default function App() {
  const [locale, setLocale] = useState<Locale>(() => {
    if (typeof window === "undefined") {
      return "zh";
    }
    const storedLocale = window.localStorage.getItem("atlas-ui-locale");
    return storedLocale === "en" ? "en" : "zh";
  });
  const [page, setPage] = useState<PageKey>("chat");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState("");
  const [activeThreadDetail, setActiveThreadDetail] = useState<ThreadDetail | null>(null);
  const [threadDetailLoading, setThreadDetailLoading] = useState(false);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedTrace, setSelectedTrace] = useState<RunTrace | null>(null);
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [memoryStatus, setMemoryStatus] = useState("");
  const [memoryError, setMemoryError] = useState("");
  const [memoryFilterType, setMemoryFilterType] = useState("all");
  const [memoryFilterQuery, setMemoryFilterQuery] = useState("");
  const [memoryPinnedOnly, setMemoryPinnedOnly] = useState(false);
  const [selectedMemoryId, setSelectedMemoryId] = useState("");
  const [memoryFormType, setMemoryFormType] = useState("semantic");
  const [memoryFormTitle, setMemoryFormTitle] = useState("");
  const [memoryFormContent, setMemoryFormContent] = useState("");
  const [memoryFormSummary, setMemoryFormSummary] = useState("");
  const [memoryFormPriority, setMemoryFormPriority] = useState("100");
  const [memoryFormMetadata, setMemoryFormMetadata] = useState("{}");
  const [traceLoading, setTraceLoading] = useState(false);
  const [isCreatingWorkspace, setIsCreatingWorkspace] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState("");
  const [chatNotice, setChatNotice] = useState("");
  const [selectedAttachments, setSelectedAttachments] = useState<string[]>([]);
  const [reindexingDocumentId, setReindexingDocumentId] = useState<string | null>(null);
  const [streamRunId, setStreamRunId] = useState("");
  const [streamSteps, setStreamSteps] = useState<StreamStep[]>([]);
  const [streamAnswerDraft, setStreamAnswerDraft] = useState("");
  const ui = UI_TEXT[locale];
  const pageCopy = PAGE_COPY[locale];

  useEffect(() => {
    void loadWorkspaces();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem("atlas-ui-locale", locale);
  }, [locale]);

  useEffect(() => {
    if (!selectedWorkspaceId) {
      return;
    }
    void Promise.all([
      loadThreads(selectedWorkspaceId),
      loadDocuments(selectedWorkspaceId),
      loadRuns(selectedWorkspaceId),
      loadMemories(selectedWorkspaceId),
    ]);
  }, [selectedWorkspaceId]);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedTrace(null);
      return;
    }
    void loadRunTrace(selectedRunId);
  }, [selectedRunId]);

  useEffect(() => {
    if (!activeThreadId) {
      setActiveThreadDetail(null);
      return;
    }
    void loadThreadDetail(activeThreadId);
  }, [activeThreadId]);

  useEffect(() => {
    setActiveThreadId("");
    setActiveThreadDetail(null);
    setStreamSteps([]);
    setStreamRunId("");
    setStreamAnswerDraft("");
    setChatNotice("");
    setChatTurns([]);
  }, [selectedWorkspaceId]);

  async function loadWorkspaces() {
    const data = await request<Workspace[]>("/workspaces");
    setWorkspaces(data);
    if (data.length > 0) {
      setSelectedWorkspaceId((current) => current || data[0].id);
    }
  }

  async function ensureDefaultWorkspace() {
    if (isCreatingWorkspace) {
      return;
    }
    setIsCreatingWorkspace(true);
    try {
      const workspace = await request<Workspace>("/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: ui.createDefaultWorkspaceName,
          slug: "atlas-demo-workspace",
          owner_user_id: OWNER_USER_ID,
          visibility: "private",
          settings_json: {},
        }),
      });
      setWorkspaces([workspace]);
      setSelectedWorkspaceId(workspace.id);
    } finally {
      setIsCreatingWorkspace(false);
    }
  }

  async function loadThreads(workspaceId: string) {
    const data = await request<Thread[]>(`/threads${buildQueryString({ workspace_id: workspaceId })}`);
    setThreads(data);
  }

  async function loadThreadDetail(threadId: string) {
    setThreadDetailLoading(true);
    try {
      const data = await request<ThreadDetail>(`/threads/${threadId}`);
      setActiveThreadDetail(data);
    } catch {
      setActiveThreadDetail(null);
    } finally {
      setThreadDetailLoading(false);
    }
  }

  async function loadDocuments(workspaceId: string) {
    const data = await request<DocumentRecord[]>(`/documents${buildQueryString({ workspace_id: workspaceId })}`);
    setDocuments(data);
    setSelectedAttachments((current) => current.filter((item) => data.some((document) => document.id === item)));
  }

  async function loadRuns(workspaceId: string) {
    const data = await request<RunSummary[]>(`/runs${buildQueryString({ workspace_id: workspaceId, limit: 24 })}`);
    setRuns(data);
    setSelectedRunId((current) => (data.some((run) => run.id === current) ? current : (data[0]?.id ?? "")));
  }

  async function loadRunTrace(runId: string) {
    setTraceLoading(true);
    try {
      const data = await request<RunTrace>(`/runs/${runId}/trace`);
      setSelectedTrace(data);
    } finally {
      setTraceLoading(false);
    }
  }

  function resetMemoryForm() {
    setSelectedMemoryId("");
    setMemoryFormType("semantic");
    setMemoryFormTitle("");
    setMemoryFormContent("");
    setMemoryFormSummary("");
    setMemoryFormPriority("100");
    setMemoryFormMetadata("{}");
  }

  function populateMemoryForm(memory: MemoryRecord) {
    setSelectedMemoryId(memory.id);
    setMemoryFormType(memory.memory_type);
    setMemoryFormTitle(memory.title);
    setMemoryFormContent(memory.content_text);
    setMemoryFormSummary(memory.summary_text ?? "");
    setMemoryFormPriority(memory.priority != null ? String(memory.priority) : "100");
    setMemoryFormMetadata(JSON.stringify(memory.metadata_json ?? {}, null, 2));
  }

  async function loadMemories(workspaceId: string) {
    setMemoryLoading(true);
    setMemoryError("");
    try {
      const data = await request<MemoryRecord[]>(
        `/memory${buildQueryString({
          workspace_id: workspaceId,
          memory_type: memoryFilterType === "all" ? undefined : memoryFilterType,
          query: memoryFilterQuery.trim() || undefined,
          pinned: memoryPinnedOnly ? true : undefined,
          limit: 100,
        })}`,
      );
      setMemories(data);
      setSelectedMemoryId((current) => (data.some((item) => item.id === current) ? current : ""));
    } catch (error) {
      setMemoryError(error instanceof Error ? error.message : ui.memoryLoadFailed);
    } finally {
      setMemoryLoading(false);
    }
  }

  async function handleRefreshMemories() {
    if (!selectedWorkspaceId) {
      return;
    }
    await loadMemories(selectedWorkspaceId);
  }

  async function handleSaveMemory() {
    if (!selectedWorkspaceId || !memoryFormTitle.trim() || !memoryFormContent.trim()) {
      return;
    }

    let metadataJson: Record<string, unknown>;
    try {
      metadataJson = JSON.parse(memoryFormMetadata || "{}") as Record<string, unknown>;
    } catch {
      setMemoryError(ui.metadataJsonInvalid);
      return;
    }

    const payload = {
      workspace_id: selectedWorkspaceId,
      memory_type: memoryFormType,
      title: memoryFormTitle.trim(),
      content_text: memoryFormContent.trim(),
      summary_text: memoryFormSummary.trim() || null,
      owner_user_id: OWNER_USER_ID,
      priority: memoryFormType === "procedural" ? Number(memoryFormPriority || 100) : null,
      metadata_json: metadataJson,
    };

    setMemoryError("");
    setMemoryStatus("");
    try {
      if (selectedMemoryId) {
        await request<MemoryRecord>(`/memory/${selectedMemoryId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: payload.title,
            content_text: payload.content_text,
            summary_text: payload.summary_text,
            priority: payload.priority,
            metadata_json: payload.metadata_json,
          }),
        });
        setMemoryStatus(ui.memoryUpdated);
      } else {
        await request<MemoryRecord>("/memory", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        setMemoryStatus(ui.memoryCreated);
      }
      await loadMemories(selectedWorkspaceId);
      resetMemoryForm();
    } catch (error) {
      setMemoryError(error instanceof Error ? error.message : ui.memorySaveFailed);
    }
  }

  async function handlePinMemory(memory: MemoryRecord) {
    try {
      await request<MemoryRecord>(`/memory/${memory.id}/pin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pinned: !memory.is_pinned }),
      });
      setMemoryStatus(memory.is_pinned ? ui.memoryUnpinned : ui.memoryPinned);
      await loadMemories(selectedWorkspaceId);
    } catch (error) {
      setMemoryError(error instanceof Error ? error.message : ui.pinUpdateFailed);
    }
  }

  async function handleDeleteMemory(memoryId: string) {
    if (!selectedWorkspaceId) {
      return;
    }
    try {
      await request<{ status: string }>(`/memory/${memoryId}`, { method: "DELETE" });
      setMemoryStatus(ui.memoryDeleted);
      await loadMemories(selectedWorkspaceId);
      if (selectedMemoryId === memoryId) {
        resetMemoryForm();
      }
    } catch (error) {
      setMemoryError(error instanceof Error ? error.message : ui.deleteFailed);
    }
  }

  async function handleUpload() {
    if (!selectedWorkspaceId || !selectedFile) {
      return;
    }

    setUploading(true);
    setUploadMessage("");
    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("workspace_id", selectedWorkspaceId);
    formData.append("owner_user_id", OWNER_USER_ID);

    try {
      const result = await request<{ status: string; duplicate_of?: string | null }>("/documents/upload", {
        method: "POST",
        body: formData,
      });
      setUploadMessage(
        result.duplicate_of
          ? fillTemplate(ui.duplicateDetected, { documentId: result.duplicate_of })
          : fillTemplate(ui.uploadFinished, { status: formatStatus(locale, result.status) }),
      );
      setSelectedFile(null);
      await loadDocuments(selectedWorkspaceId);
    } catch (error) {
      setUploadMessage(error instanceof Error ? error.message : ui.uploadFailed);
    } finally {
      setUploading(false);
    }
  }

  async function runStreamedChat(
    path: string,
    body: Record<string, unknown>,
    options: {
      question?: string;
      clearInputOnSuccess?: boolean;
      fallbackQuestion?: string;
    } = {},
  ) {
    setChatLoading(true);
    setChatError("");
    setChatNotice("");
    setStreamRunId("");
    setStreamSteps([]);
    setStreamAnswerDraft("");
    let latestRunId = "";
    let latestThreadId = activeThreadId;
    let resolvedQuestion = options.question ?? "";

    try {
      await streamRequest(path, body, (event) => {
        if (event.event === "run_created") {
          latestRunId = event.data.run_id;
          latestThreadId = event.data.thread_id;
          resolvedQuestion = event.data.question ?? resolvedQuestion;
          setStreamRunId(event.data.run_id);
          setActiveThreadId(event.data.thread_id);
          setSelectedRunId(event.data.run_id);
        }

        if (event.event === "step") {
          setStreamSteps((current) =>
            upsertStreamStep(current, {
              stepKey: event.data.step_key,
              stepType: event.data.step_type,
              status: event.data.status,
              startedAt: event.data.started_at,
              endedAt: event.data.ended_at,
              durationMs: event.data.duration_ms,
              preview: summarizeOutput(locale, event.data.output) || event.data.error?.message || "",
              errorMessage: event.data.error?.message,
            }),
          );
        }

        if (event.event === "token") {
          latestRunId = event.data.run_id;
          setStreamAnswerDraft(event.data.answer);
        }

        if (event.event === "cancelled") {
          latestRunId = event.data.run_id;
          latestThreadId = event.data.thread_id;
          resolvedQuestion = event.data.question ?? resolvedQuestion;
          setStreamAnswerDraft(event.data.answer);
          setChatNotice(ui.generationStopped);
          setActiveThreadId(event.data.thread_id);
          setSelectedRunId(event.data.run_id);
        }

        if (event.event === "final") {
          latestRunId = event.data.run_id;
          latestThreadId = event.data.thread_id;
          resolvedQuestion = event.data.question ?? resolvedQuestion;
          setStreamAnswerDraft(event.data.answer);
          setChatNotice("");
          setChatTurns((current) => [
            ...current,
            {
              runId: event.data.run_id,
              threadId: event.data.thread_id,
              question:
                resolvedQuestion ||
                options.fallbackQuestion ||
                fillTemplate(ui.retryOfRun, { runId: (event.data.retry_of_run_id ?? "").slice(0, 8) }),
              answer: event.data.answer,
              evidenceGrade: event.data.evidence_grade,
              citations: event.data.citations,
            },
          ]);
          if (options.clearInputOnSuccess) {
            setChatInput("");
          }
          setActiveThreadId(event.data.thread_id);
          setSelectedRunId(event.data.run_id);
        }

        if (event.event === "error") {
          setChatError(`${event.data.type}: ${event.data.message}`);
          if (event.data.run_id) {
            setSelectedRunId(event.data.run_id);
          }
        }
      });

      await Promise.all([
        loadThreads(selectedWorkspaceId),
        loadRuns(selectedWorkspaceId),
        latestThreadId ? loadThreadDetail(latestThreadId) : Promise.resolve(),
        latestRunId ? loadRunTrace(latestRunId) : Promise.resolve(),
      ]);
    } catch (error) {
      setChatError(error instanceof Error ? error.message : ui.chatFailed);
    } finally {
      setChatLoading(false);
    }
  }

  async function handleChat() {
    if (!selectedWorkspaceId || !chatInput.trim()) {
      return;
    }

    const question = chatInput.trim();
    const requestedMode = "auto";
    await runStreamedChat(
      "/chat/stream",
      {
        thread_id: activeThreadId || undefined,
        workspace_id: selectedWorkspaceId,
        message: question,
        attachments: selectedAttachments,
        mode: requestedMode,
        user_id: OWNER_USER_ID,
      },
      {
        question,
        clearInputOnSuccess: true,
      },
    );
  }

  async function handleRetryRun(runId: string, questionHint?: string) {
    if (!selectedWorkspaceId || !runId || chatLoading) {
      return;
    }

    setPage("chat");
    await runStreamedChat(`/runs/${runId}/retry/stream`, {}, { fallbackQuestion: questionHint });
  }

  async function handleStopStreaming() {
    if (!streamRunId) {
      return;
    }

    try {
      const result = await request<{ accepted: boolean; status: string }>(`/runs/${streamRunId}/cancel`, {
        method: "POST",
      });
      setChatNotice(
        result.accepted
          ? ui.stoppingGeneration
          : fillTemplate(ui.runStatusLine, { status: formatStatus(locale, result.status) }),
      );
    } catch (error) {
      setChatError(error instanceof Error ? error.message : ui.stopFailed);
    }
  }

  async function handleReindex(documentId: string) {
    if (!selectedWorkspaceId) {
      return;
    }

    setReindexingDocumentId(documentId);
    setUploadMessage("");
    try {
      const result = await request<{ status: string }>(`/documents/${documentId}/reindex`, {
        method: "POST",
      });
      setUploadMessage(fillTemplate(ui.reindexFinished, { status: formatStatus(locale, result.status) }));
      await loadDocuments(selectedWorkspaceId);
    } catch (error) {
      setUploadMessage(error instanceof Error ? error.message : ui.reindexFailed);
    } finally {
      setReindexingDocumentId(null);
    }
  }

  function toggleAttachment(documentId: string) {
    setSelectedAttachments((current) =>
      current.includes(documentId) ? current.filter((item) => item !== documentId) : [...current, documentId],
    );
  }

  function openTrace(runId: string) {
    setSelectedRunId(runId);
    setPage("trace");
  }

  function startNewThread() {
    setActiveThreadId("");
    setActiveThreadDetail(null);
    setStreamSteps([]);
    setStreamRunId("");
    setStreamAnswerDraft("");
    setChatNotice("");
  }

  const currentPage = pageCopy[page];
  const visibleChatTurns = activeThreadId
    ? chatTurns.filter((turn) => turn.threadId === activeThreadId)
    : chatTurns;
  const latestChatTurn = visibleChatTurns.length > 0 ? visibleChatTurns[visibleChatTurns.length - 1] : null;
  const retryableRunId = streamRunId || latestChatTurn?.runId || "";
  const selectedMemory = memories.find((memory) => memory.id === selectedMemoryId) ?? null;
  const nextLocale: Locale = locale === "zh" ? "en" : "zh";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">AT</div>
          <div>
            <strong>Atlas</strong>
            <p>{ui.brandSubtitle}</p>
          </div>
        </div>
        <nav className="nav-list">
          {PAGE_KEYS.map((key) => (
            <button
              key={key}
              className={page === key ? "nav-item active" : "nav-item"}
              onClick={() => setPage(key)}
            >
              {pageCopy[key].label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <h1>{currentPage?.label}</h1>
            <p>{currentPage?.description}</p>
          </div>

          <div className="workspace-control">
            <button className="secondary-button mini-button" onClick={() => setLocale(nextLocale)} title={ui.language}>
              {locale === "zh" ? ui.switchToEnglish : ui.switchToChinese}
            </button>
            {workspaces.length > 0 ? (
              <select value={selectedWorkspaceId} onChange={(event) => setSelectedWorkspaceId(event.target.value)}>
                {workspaces.map((workspace) => (
                  <option key={workspace.id} value={workspace.id}>
                    {workspace.name}
                  </option>
                ))}
              </select>
            ) : (
              <button onClick={() => void ensureDefaultWorkspace()} disabled={isCreatingWorkspace}>
                {isCreatingWorkspace ? ui.creating : ui.createDefaultWorkspace}
              </button>
            )}
          </div>
        </header>

        <section className="summary-grid">
          <article className="summary-card">
            <span>{ui.workspaces}</span>
            <strong>{workspaces.length}</strong>
          </article>
          <article className="summary-card">
            <span>{ui.threads}</span>
            <strong>{threads.length}</strong>
          </article>
          <article className="summary-card">
            <span>{ui.runs}</span>
            <strong>{runs.length}</strong>
          </article>
        </section>

        {page === "kb" ? (
          <section className="panel-grid">
            <article className="panel">
              <div className="panel-header">
                <h2>{ui.documentUpload}</h2>
                <p>{ui.documentUploadDesc}</p>
              </div>
              <input
                type="file"
                onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                accept=".pdf,.docx,.pptx,.md,.txt"
              />
              <button onClick={() => void handleUpload()} disabled={!selectedFile || !selectedWorkspaceId || uploading}>
                {uploading ? ui.uploading : ui.uploadAndParse}
              </button>
              {uploadMessage ? <p className="status-text">{uploadMessage}</p> : null}
            </article>

            <article className="panel">
              <div className="panel-header">
                <h2>{ui.knowledgeBase}</h2>
                <p>{ui.knowledgeBaseDesc}</p>
              </div>
              <div className="table-list">
                {documents.length === 0 ? (
                  <p className="empty-state">{ui.noDocuments}</p>
                ) : (
                  documents.map((document) => (
                    <div key={document.id} className="table-row">
                      <div>
                        <strong>{document.title}</strong>
                        <p>{document.original_filename}</p>
                      </div>
                      <div className="pill-group">
                        <span className="pill">{document.file_type}</span>
                        <span className="pill">{formatStatus(locale, document.status)}</span>
                        <button
                          className="mini-button"
                          onClick={() => void handleReindex(document.id)}
                          disabled={reindexingDocumentId === document.id}
                        >
                          {reindexingDocumentId === document.id ? ui.reindexing : ui.reindex}
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </article>
          </section>
        ) : null}

        {page === "chat" ? (
          <section className="panel-grid">
            <article className="panel">
              <div className="panel-header">
                <div>
                  <h2>{ui.threadListTitle}</h2>
                  <p>{ui.threadListDesc}</p>
                </div>
                <button className="secondary-button mini-button" onClick={startNewThread}>
                  {ui.newThread}
                </button>
              </div>
              <div className="table-list">
                {threads.length === 0 ? (
                  <p className="empty-state">{ui.noThreads}</p>
                ) : (
                  threads.map((thread) => (
                    <button
                      key={thread.id}
                      className={activeThreadId === thread.id ? "trace-run-button active" : "trace-run-button"}
                      onClick={() => setActiveThreadId(thread.id)}
                    >
                      <div>
                        <strong>{thread.title}</strong>
                        <p>
                          {ui.modePrefix}={formatMode(locale, thread.mode)}
                        </p>
                      </div>
                      <div className="trace-run-meta">
                        {activeThreadId === thread.id ? <span className="pill">{ui.active}</span> : null}
                        <span className="pill">{formatStatus(locale, thread.status)}</span>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </article>

            <article className="panel">
              <div className="panel-header">
                <h2>{ui.streamChatTitle}</h2>
                <p>{ui.streamChatDesc}</p>
              </div>
              <textarea
                className="chat-input"
                placeholder={ui.chatPlaceholder}
                value={chatInput}
                onChange={(event) => setChatInput(event.target.value)}
              />
              <div className="attachment-list">
                {documents.map((document) => (
                  <label key={document.id} className="attachment-item">
                    <input
                      type="checkbox"
                      checked={selectedAttachments.includes(document.id)}
                      onChange={() => toggleAttachment(document.id)}
                    />
                    <span>{document.title}</span>
                  </label>
                ))}
              </div>

              <div className="chat-toolbar">
                <button
                  onClick={() => void handleChat()}
                  disabled={!chatInput.trim() || chatLoading || !selectedWorkspaceId}
                >
                  {chatLoading ? ui.streaming : ui.sendQuestion}
                </button>
                {chatLoading && streamRunId ? (
                  <button className="danger-button" onClick={() => void handleStopStreaming()}>
                    {ui.stop}
                  </button>
                ) : null}
                {!chatLoading && retryableRunId ? (
                  <button
                    className="secondary-button"
                    onClick={() => void handleRetryRun(retryableRunId, latestChatTurn?.question)}
                  >
                    {ui.retryLastRun}
                  </button>
                ) : null}
                {streamRunId ? (
                  <button className="secondary-button" onClick={() => openTrace(streamRunId)}>
                    {ui.openCurrentTrace}
                  </button>
                ) : null}
              </div>

              {activeThreadId ? (
                <div className="thread-context-panel">
                  <div className="thread-context-head">
                    <strong>{activeThreadDetail?.title ?? ui.currentThread}</strong>
                    <span className="pill">
                      {activeThreadDetail?.mode ? formatMode(locale, activeThreadDetail.mode) : ui.loading}
                    </span>
                  </div>
                  {threadDetailLoading ? (
                    <p className="empty-state">{ui.loadingThreadHistory}</p>
                  ) : activeThreadDetail ? (
                    <>
                      {activeThreadDetail.thread_summary ? (
                        <div className="thread-summary-card">
                          <strong>{ui.compressedBackground}</strong>
                          <p>{activeThreadDetail.thread_summary}</p>
                        </div>
                      ) : null}
                      <div className="thread-message-list">
                        {activeThreadDetail.messages.slice(-6).map((message) => (
                          <div key={message.id} className={`thread-message thread-message-${message.role}`}>
                            <strong>{message.role === "user" ? ui.userLabel : ui.assistantLabel}</strong>
                            <p>{message.content_text}</p>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p className="empty-state">{ui.threadHistoryUnavailable}</p>
                  )}
                </div>
              ) : (
                <p className="empty-state">{ui.noThreadSelected}</p>
              )}

              {streamAnswerDraft ? (
                <div className="stream-answer-panel">
                  <strong>{ui.liveAnswerDraft}</strong>
                  <p>{streamAnswerDraft}</p>
                </div>
              ) : null}

              {streamSteps.length > 0 ? (
                <div className="stream-panel">
                  <strong>{ui.liveGraphProgress}</strong>
                  <div className="stream-step-list">
                    {streamSteps.map((step) => (
                      <div key={step.stepKey} className={`stream-step stream-step-${step.status}`}>
                        <div>
                          <strong>{getStepLabel(locale, step.stepKey)}</strong>
                          <small>{getStepTypeLabel(locale, step.stepKey, step.stepType)}</small>
                        </div>
                        <div className="stream-step-meta">
                          <span className={`status-pill status-pill-${step.status}`}>{formatStepStatus(locale, step.status)}</span>
                          <small>{getStepNarrative(locale, step.stepKey, step.status, step.preview, step.errorMessage)}</small>
                          <small>{step.durationMs != null ? formatDuration(step.durationMs) : ui.inProgress}</small>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {chatNotice ? <p className="status-text">{chatNotice}</p> : null}
              {chatError ? <p className="error-text">{chatError}</p> : null}

              <div className="chat-turns">
                {visibleChatTurns.length === 0 ? (
                  <p className="empty-state">{ui.answersAppearHere}</p>
                ) : (
                  visibleChatTurns.map((turn) => (
                    <div key={turn.runId} className="chat-turn">
                      <div className="chat-turn-head">
                        <strong>
                          {ui.questionPrefix} {turn.question}
                        </strong>
                        <div className="pill-group">
                          <button
                            className="secondary-button mini-button"
                            onClick={() => void handleRetryRun(turn.runId, turn.question)}
                          >
                            {ui.regenerate}
                          </button>
                          <button className="secondary-button mini-button" onClick={() => openTrace(turn.runId)}>
                            {ui.viewTrace}
                          </button>
                        </div>
                      </div>
                      <p>
                        {ui.answerPrefix} {turn.answer}
                      </p>
                      <p className="status-text">
                        {ui.evidencePrefix}
                        {formatStatus(locale, turn.evidenceGrade)}
                      </p>
                      {turn.citations.map((citation) => (
                        <div key={citation.chunk_id + citation.citation_label} className="citation-card">
                          <strong>{citation.citation_label}</strong>
                          <p>{citation.section_path.join(" > ")}</p>
                          <p>{citation.snippet}</p>
                        </div>
                      ))}
                    </div>
                  ))
                )}
              </div>
            </article>
          </section>
        ) : null}

        {page === "trace" ? (
          <section className="trace-layout">
            <article className="panel">
              <div className="panel-header">
                <h2>{ui.recentRuns}</h2>
                <p>{ui.recentRunsDesc}</p>
              </div>
              <div className="trace-run-list">
                {runs.length === 0 ? (
                  <p className="empty-state">{ui.noRuns}</p>
                ) : (
                  runs.map((run) => (
                    <button
                      key={run.id}
                      className={selectedRunId === run.id ? "trace-run-button active" : "trace-run-button"}
                      onClick={() => setSelectedRunId(run.id)}
                    >
                      <div>
                        <strong>{formatRequestType(locale, run.request_type)}</strong>
                        <p>{formatDate(locale, run.started_at)}</p>
                      </div>
                      <div className="trace-run-meta">
                        <span className="pill">{formatStatus(locale, run.status)}</span>
                        <span className="pill">
                          {run.evidence_grade ? formatStatus(locale, run.evidence_grade) : "-"}
                        </span>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </article>

            <article className="panel trace-detail">
              <div className="panel-header">
                <div>
                  <h2>{ui.runTrace}</h2>
                  <p>{ui.runTraceDesc}</p>
                </div>
                {selectedRunId ? (
                  <button
                    className="secondary-button mini-button"
                    onClick={() =>
                      void handleRetryRun(
                        selectedRunId,
                        chatTurns.find((turn) => turn.runId === selectedRunId)?.question,
                      )
                    }
                    disabled={chatLoading}
                  >
                    {ui.retrySelectedRun}
                  </button>
                ) : null}
              </div>

              {traceLoading ? (
                <p className="empty-state">{ui.loadingTrace}</p>
              ) : selectedTrace ? (
                <>
                  <section className="trace-summary-grid">
                    <article className="summary-card compact">
                      <span>{ui.status}</span>
                      <strong>{formatStatus(locale, selectedTrace.run.status)}</strong>
                    </article>
                    <article className="summary-card compact">
                      <span>{ui.route}</span>
                      <strong>{formatRoute(locale, selectedTrace.run.route_target)}</strong>
                    </article>
                    <article className="summary-card compact">
                      <span>{ui.evidence}</span>
                      <strong>
                        {selectedTrace.run.evidence_grade ? formatStatus(locale, selectedTrace.run.evidence_grade) : "-"}
                      </strong>
                    </article>
                  </section>

                  {selectedTrace.run.error_message ? (
                    <p className="error-text">
                      {selectedTrace.run.error_code}: {selectedTrace.run.error_message}
                    </p>
                  ) : null}

                  <section className="trace-section">
                    <div className="trace-section-head">
                      <h3>{ui.steps}</h3>
                      <span>{selectedTrace.steps.length}</span>
                    </div>
                    <div className="trace-card-list">
                      {selectedTrace.steps.map((step) => (
                        <div key={step.id} className="trace-step-card">
                          <div className="trace-card-head">
                            <div>
                              <strong>{getStepLabel(locale, step.step_key)}</strong>
                              <p className="trace-step-subtitle">{getStepTypeLabel(locale, step.step_key, step.step_type)}</p>
                            </div>
                            <div className="trace-step-meta">
                              <span className={`status-pill status-pill-${step.status}`}>{formatStepStatus(locale, step.status)}</span>
                              <small>{formatDuration(getDurationFromTimestamps(step.started_at, step.ended_at))}</small>
                            </div>
                          </div>
                          <p>{getStepNarrative(locale, step.step_key, step.status, summarizeOutput(locale, step.output_json), step.error_message ?? undefined)}</p>
                          <pre className="mono-block">{JSON.stringify(step.output_json, null, 2)}</pre>
                        </div>
                      ))}
                    </div>
                  </section>

                  <section className="trace-section">
                    <div className="trace-section-head">
                      <h3>{ui.snapshots}</h3>
                      <span>{selectedTrace.snapshots.length}</span>
                    </div>
                    <div className="trace-card-list">
                      {selectedTrace.snapshots.map((snapshot) => (
                        <div key={snapshot.id} className="trace-snapshot-card">
                          <div className="trace-card-head">
                            <strong>
                              #{snapshot.snapshot_index} {getStepLabel(locale, snapshot.step_key)}
                            </strong>
                            <span>{formatDate(locale, snapshot.created_at)}</span>
                          </div>
                          <pre className="mono-block">{JSON.stringify(snapshot.state_json, null, 2)}</pre>
                        </div>
                      ))}
                    </div>
                  </section>
                </>
              ) : (
                <p className="empty-state">{ui.selectRun}</p>
              )}
            </article>
          </section>
        ) : null}

        {page === "memory" ? (
          <section className="memory-layout">
            <article className="panel">
              <div className="panel-header">
                <div>
                  <h2>{ui.memoryInventory}</h2>
                  <p>{ui.memoryInventoryDesc}</p>
                </div>
                <button className="secondary-button mini-button" onClick={() => void handleRefreshMemories()}>
                  {ui.refresh}
                </button>
              </div>

              <div className="memory-filter-grid">
                <select value={memoryFilterType} onChange={(event) => setMemoryFilterType(event.target.value)}>
                  <option value="all">{ui.allTypes}</option>
                  <option value="semantic">{ui.semantic}</option>
                  <option value="episodic">{ui.episodic}</option>
                  <option value="procedural">{ui.procedural}</option>
                </select>
                <input
                  type="text"
                  placeholder={ui.searchTitleOrContent}
                  value={memoryFilterQuery}
                  onChange={(event) => setMemoryFilterQuery(event.target.value)}
                />
                <label className="attachment-item">
                  <input
                    type="checkbox"
                    checked={memoryPinnedOnly}
                    onChange={(event) => setMemoryPinnedOnly(event.target.checked)}
                  />
                  <span>{ui.pinnedOnly}</span>
                </label>
                <button onClick={() => void handleRefreshMemories()} disabled={!selectedWorkspaceId || memoryLoading}>
                  {memoryLoading ? ui.loading : ui.applyFilters}
                </button>
              </div>

              <div className="table-list">
                {memories.length === 0 ? (
                  <p className="empty-state">{ui.noMemories}</p>
                ) : (
                  memories.map((memory) => (
                    <div key={memory.id} className={selectedMemoryId === memory.id ? "memory-card active" : "memory-card"}>
                      <button className="memory-card-main" onClick={() => populateMemoryForm(memory)}>
                        <div>
                          <strong>{memory.title}</strong>
                          <p>{memory.summary_text ?? memory.content_text.slice(0, 140)}</p>
                        </div>
                        <div className="pill-group">
                          <span className="pill">{formatMemoryType(locale, memory.memory_type)}</span>
                          {memory.is_pinned ? <span className="pill">{ui.pinned}</span> : null}
                          {memory.score != null ? <span className="pill">{ui.score}={memory.score.toFixed(2)}</span> : null}
                        </div>
                      </button>
                      <div className="memory-card-actions">
                        <button className="secondary-button mini-button" onClick={() => void handlePinMemory(memory)}>
                          {memory.is_pinned ? ui.unpin : ui.pin}
                        </button>
                        {memory.source_run_id ? (
                          <button className="secondary-button mini-button" onClick={() => openTrace(memory.source_run_id!)}>
                            {ui.sourceRun}
                          </button>
                        ) : null}
                        <button className="danger-button mini-button" onClick={() => void handleDeleteMemory(memory.id)}>
                          {ui.delete}
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <h2>{selectedMemory ? ui.editMemory : ui.createMemory}</h2>
                  <p>{ui.memoryFormDesc}</p>
                </div>
                <button className="secondary-button mini-button" onClick={resetMemoryForm}>
                  {ui.newRecord}
                </button>
              </div>

              <div className="memory-form-grid">
                <label>
                  <span>{ui.memoryType}</span>
                  <select value={memoryFormType} onChange={(event) => setMemoryFormType(event.target.value)}>
                    <option value="semantic">{ui.semantic}</option>
                    <option value="episodic">{ui.episodic}</option>
                    <option value="procedural">{ui.procedural}</option>
                  </select>
                </label>
                <label>
                  <span>{ui.priority}</span>
                  <input
                    type="number"
                    value={memoryFormPriority}
                    onChange={(event) => setMemoryFormPriority(event.target.value)}
                    disabled={memoryFormType !== "procedural"}
                  />
                </label>
                <label className="memory-form-wide">
                  <span>{ui.title}</span>
                  <input type="text" value={memoryFormTitle} onChange={(event) => setMemoryFormTitle(event.target.value)} />
                </label>
                <label className="memory-form-wide">
                  <span>{ui.summary}</span>
                  <textarea
                    className="chat-input memory-textarea"
                    value={memoryFormSummary}
                    onChange={(event) => setMemoryFormSummary(event.target.value)}
                    placeholder={ui.summaryPlaceholder}
                  />
                </label>
                <label className="memory-form-wide">
                  <span>{ui.content}</span>
                  <textarea
                    className="chat-input memory-textarea"
                    value={memoryFormContent}
                    onChange={(event) => setMemoryFormContent(event.target.value)}
                    placeholder={ui.contentPlaceholder}
                  />
                </label>
                <label className="memory-form-wide">
                  <span>{ui.metadataJson}</span>
                  <textarea
                    className="chat-input memory-textarea mono-input"
                    value={memoryFormMetadata}
                    onChange={(event) => setMemoryFormMetadata(event.target.value)}
                  />
                </label>
              </div>

              <div className="chat-toolbar">
                <button onClick={() => void handleSaveMemory()} disabled={!selectedWorkspaceId}>
                  {selectedMemory ? ui.saveChanges : ui.createMemory}
                </button>
                {selectedMemory ? (
                  <button className="secondary-button" onClick={() => populateMemoryForm(selectedMemory)}>
                    {ui.reloadSelected}
                  </button>
                ) : null}
              </div>

              {memoryStatus ? <p className="status-text">{memoryStatus}</p> : null}
              {memoryError ? <p className="error-text">{memoryError}</p> : null}
            </article>
          </section>
        ) : null}

        {page !== "kb" && page !== "chat" && page !== "trace" && page !== "memory" ? (
          <section className="panel-grid">
            <article className="panel">
              <div className="panel-header">
                <h2>{currentPage?.label}</h2>
                <p>{ui.reservedDesc}</p>
              </div>
            </article>
          </section>
        ) : null}
      </main>
    </div>
  );
}
