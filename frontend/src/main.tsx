import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Brain,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Database,
  FileText,
  Loader2,
  MessageSquare,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings,
  Square,
  Trash2,
  X,
} from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const PROMPT_STORAGE_KEY = "stockai.chat.prompts";

type PromptPreset = {
  id: string;
  title: string;
  content: string;
};

const DEFAULT_PROMPTS: PromptPreset[] = [
  {
    id: "key-facts",
    title: "提炼关键事实",
    content: "请基于公告原文，提炼这条公告最重要的事实、涉及金额/比例/时间点，以及对公司的直接影响。",
  },
  {
    id: "risk-check",
    title: "风险核查",
    content: "请只从公告原文出发，列出这条公告需要警惕的风险点，并说明哪些风险还需要后续验证。",
  },
  {
    id: "action",
    title: "行动建议",
    content: "请给出明确结论：这条公告是否需要继续关注？如果需要，下一步应该验证哪些信息；如果不需要，请说明原因。不要给买入或卖出指令。",
  },
];

type Announcement = {
  id: number;
  code: string;
  name: string;
  title: string;
  announcement_type: string;
  announcement_date: string;
  url: string;
  source: string;
  is_important: boolean;
  matched_keywords: string[];
  ai_screen_status: string;
  ai_worth_tracking?: boolean | null;
  ai_importance_score?: number | null;
  ai_event_type?: string | null;
  ai_screen_reason?: string | null;
  parse_status: string;
  analysis_status: string;
};

type AnnouncementDetail = Announcement & {
  content?: string | null;
  content_length: number;
};

type AnnouncementResponse = {
  items: Announcement[];
  total: number;
  page: number;
  page_size: number;
};

type FilterOptions = {
  dates: string[];
  announcement_types: string[];
};

type DatabaseSummary = {
  total_announcements: number;
  ai_tracking_announcements: number;
  analyzed_announcements: number;
  content_announcements: number;
  chat_messages: number;
};

type Analysis = {
  announcement_id: number;
  provider: string;
  model: string;
  output_format: string;
  free_output: string;
  summary: string;
  sentiment: string;
  importance_score: number;
  risk_points: string[];
  opportunities: string[];
  watch_signals: string[];
  action_suggestion: string;
  confidence: number;
  reasoning_short: string;
  not_investment_advice: string;
};

type AnalysisJobStatus = {
  running: boolean;
  cancel_requested: boolean;
  requested: number;
  analyzed: number;
  failed: number;
  current_id?: number | null;
  message: string;
};

type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  provider?: string | null;
  model?: string | null;
  content_length: number;
  created_at: string;
};

type ChatResponse = {
  answer: string;
  content_length: number;
  content_preview: string;
  provider: string;
  model: string;
};

type ModelSettingsState = {
  provider: "mock" | "openai" | "openai-compatible";
  model: string;
  base_url: string;
  api_key: string;
  has_api_key?: boolean;
};

type AnalysisPromptPreset = {
  id: string;
  title: string;
  system_prompt: string;
  user_instruction: string;
  is_active: boolean;
};

type ResearchReportSummary = {
  id: number;
  report_name: string;
  source: string;
  created_at: string;
  updated_at: string;
  analysis_status: string;
};

type ResearchReportDetail = ResearchReportSummary & {
  translated_text: string;
  analysis_output?: string | null;
  analysis_provider?: string | null;
  analysis_model?: string | null;
  analysis_error?: string | null;
};

type ResearchReportResponse = {
  items: ResearchReportSummary[];
  total: number;
};

function todayYmd() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
}

function ymdToDateInput(value: string) {
  if (!/^\d{8}$/.test(value)) return "";
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function dateInputToYmd(value: string) {
  return value.replace(/-/g, "");
}

function loadPromptPresets(): PromptPreset[] {
  try {
    const raw = window.localStorage.getItem(PROMPT_STORAGE_KEY);
    if (!raw) return DEFAULT_PROMPTS;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return DEFAULT_PROMPTS;
    const prompts = parsed.filter((item) => item?.id && item?.title && item?.content);
    return prompts.length ? prompts : DEFAULT_PROMPTS;
  } catch {
    return DEFAULT_PROMPTS;
  }
}

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function App() {
  const [view, setView] = useState<"workspace" | "research" | "settings">("workspace");
  const [date, setDate] = useState(todayYmd());
  const [keyword, setKeyword] = useState("");
  const [announcementType, setAnnouncementType] = useState("");
  const [aiOnly, setAiOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<AnnouncementResponse>({ items: [], total: 0, page: 1, page_size: 30 });
  const [summary, setSummary] = useState<DatabaseSummary | null>(null);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({ dates: [], announcement_types: [] });
  const [selected, setSelected] = useState<AnnouncementDetail | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analysisJob, setAnalysisJob] = useState<AnalysisJobStatus | null>(null);
  const [chatQuestion, setChatQuestion] = useState("请基于公告原文，说明这条公告最重要的事实、风险和需要继续验证的问题。");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatMeta, setChatMeta] = useState<ChatResponse | null>(null);
  const [chatPromptOpen, setChatPromptOpen] = useState(false);
  const [promptPresets, setPromptPresets] = useState<PromptPreset[]>(loadPromptPresets);
  const [promptDraftId, setPromptDraftId] = useState("");
  const [promptDraftTitle, setPromptDraftTitle] = useState("");
  const [promptDraftContent, setPromptDraftContent] = useState("");
  const [settings, setSettings] = useState<ModelSettingsState>({
    provider: "mock",
    model: "mock-free-test",
    base_url: "",
    api_key: "",
  });
  const [analysisPrompts, setAnalysisPrompts] = useState<AnalysisPromptPreset[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [loading, setLoading] = useState("");
  const [message, setMessage] = useState("");

  const query = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "30" });
    if (date) params.set("date", date);
    if (keyword) params.set("keyword", keyword);
    if (announcementType) params.set("announcement_type", announcementType);
    if (aiOnly) params.set("ai_worth_tracking", "true");
    return params.toString();
  }, [aiOnly, announcementType, date, keyword, page]);

  async function loadAnnouncements(autoSelect = true) {
    setLoading("list");
    try {
      const result = await api<AnnouncementResponse>(`/api/announcements?${query}`);
      setData(result);
      if (autoSelect && result.items.length && !selected) {
        await selectAnnouncement(result.items[0]);
      }
    } finally {
      setLoading("");
    }
  }

  async function loadOverview() {
    const [options, dbSummary] = await Promise.all([
      api<FilterOptions>("/api/filter-options"),
      api<DatabaseSummary>("/api/database/summary"),
    ]);
    setFilterOptions(options);
    setSummary(dbSummary);
  }

  async function loadSettings() {
    const result = await api<{ provider: ModelSettingsState["provider"]; model: string; base_url?: string | null; has_api_key: boolean }>(
      "/api/settings/models",
    );
    setSettings({
      provider: result.provider,
      model: result.model,
      base_url: result.base_url ?? "",
      api_key: "",
      has_api_key: result.has_api_key,
    });
  }

  async function loadAnalysisPrompts() {
    const result = await api<{ items: AnalysisPromptPreset[] }>("/api/settings/analysis-prompts");
    setAnalysisPrompts(result.items);
  }

  async function loadAnalysisJob() {
    setAnalysisJob(await api<AnalysisJobStatus>("/api/analysis/auto/status"));
  }

  useEffect(() => {
    loadAnnouncements().catch((error) => setMessage(error.message));
  }, [query]);

  useEffect(() => {
    loadOverview().catch((error) => setMessage(error.message));
    loadSettings().catch((error) => setMessage(error.message));
    loadAnalysisPrompts().catch((error) => setMessage(error.message));
    loadAnalysisJob().catch((error) => setMessage(error.message));
  }, []);

  useEffect(() => {
    if (!analysisJob?.running) return;
    const timer = window.setInterval(() => {
      loadAnalysisJob().catch((error) => setMessage(error.message));
      loadOverview().catch((error) => setMessage(error.message));
      loadAnnouncements(false).catch((error) => setMessage(error.message));
      if (selected) refreshSelectedAnnouncement(selected.id).catch((error) => setMessage(error.message));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [analysisJob?.running, selected?.id, query]);

  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(""), 4500);
    return () => window.clearTimeout(timer);
  }, [message]);

  useEffect(() => {
    setPage(1);
    setSelected(null);
    setAnalysis(null);
    setChatMessages([]);
    setChatMeta(null);
    setSelectedIds([]);
  }, [aiOnly, announcementType, date, keyword]);

  async function fetchAnnouncements() {
    setLoading("fetch");
    try {
      const result = await api<{ fetched: number; inserted: number; updated: number; important: number; screened: number }>("/api/fetch-announcements", {
        method: "POST",
        body: JSON.stringify({ date }),
      });
      setMessage(`抓取 ${result.fetched} 条，新增 ${result.inserted} 条，初筛 ${result.screened} 条，关注 ${result.important} 条`);
      await loadOverview();
      await loadAnnouncements();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "抓取失败");
    } finally {
      setLoading("");
    }
  }

  async function screenAnnouncements() {
    setLoading("screen");
    try {
      const limit = Math.min(Math.max(summary?.total_announcements ?? 500, 500), 5000);
      const result = await api<{ requested: number; screened: number; failed: number }>("/api/screen/run", {
        method: "POST",
        body: JSON.stringify({ date, limit, reset: true }),
      });
      setMessage(`重新初筛 ${result.requested} 条，完成 ${result.screened} 条，失败 ${result.failed} 条`);
      await loadOverview();
      await loadAnnouncements();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "初筛失败");
    } finally {
      setLoading("");
    }
  }

  async function startAutoAnalysis() {
    setLoading("autoAnalyze");
    try {
      const hasSelected = selectedIds.length > 0;
      const limit = hasSelected ? selectedIds.length : Math.min(Math.max(summary?.ai_tracking_announcements ?? 500, 500), 5000);
      const result = await api<AnalysisJobStatus>("/api/analysis/auto/start", {
        method: "POST",
        body: JSON.stringify({ date, limit, announcement_ids: hasSelected ? selectedIds : null }),
      });
      setAnalysisJob(result);
      setMessage(result.message || "自动分析已启动");
      await loadOverview();
      await loadAnnouncements();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "自动分析启动失败");
    } finally {
      setLoading("");
    }
  }

  async function cancelAutoAnalysis() {
    setLoading("cancelAnalyze");
    try {
      const result = await api<AnalysisJobStatus>("/api/analysis/auto/cancel", { method: "POST" });
      setAnalysisJob(result);
      setMessage(result.message);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "取消分析失败");
    } finally {
      setLoading("");
    }
  }

  async function analyzeOne(item: Announcement) {
    setLoading(`analyze-${item.id}`);
    try {
      const result = await api<Analysis>(`/api/announcements/${item.id}/analyze`, { method: "POST" });
      if (selected?.id === item.id) {
        setAnalysis(result);
        await refreshSelectedAnnouncement(item.id);
      }
      setMessage("分析完成");
      await loadOverview();
      await loadAnnouncements(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "分析失败");
    } finally {
      setLoading("");
    }
  }

  function toggleSelectedId(id: number, checked: boolean) {
    setSelectedIds((current) => (checked ? [...new Set([...current, id])] : current.filter((item) => item !== id)));
  }

  function togglePageSelection(checked: boolean) {
    setSelectedIds((current) => {
      const pageIds = data.items.map((item) => item.id);
      if (checked) return [...new Set([...current, ...pageIds])];
      return current.filter((id) => !pageIds.includes(id));
    });
  }

  function savePromptPresets(next: PromptPreset[]) {
    setPromptPresets(next);
    window.localStorage.setItem(PROMPT_STORAGE_KEY, JSON.stringify(next));
  }

  function editPrompt(prompt: PromptPreset) {
    setPromptDraftId(prompt.id);
    setPromptDraftTitle(prompt.title);
    setPromptDraftContent(prompt.content);
  }

  function savePromptDraft() {
    const title = promptDraftTitle.trim();
    const content = promptDraftContent.trim();
    if (!title || !content) return;
    const id = promptDraftId || crypto.randomUUID();
    const next = promptPresets.some((item) => item.id === id)
      ? promptPresets.map((item) => (item.id === id ? { id, title, content } : item))
      : [...promptPresets, { id, title, content }];
    savePromptPresets(next);
    setPromptDraftId("");
    setPromptDraftTitle("");
    setPromptDraftContent("");
  }

  function deletePromptDraft() {
    if (!promptDraftId) return;
    savePromptPresets(promptPresets.filter((item) => item.id !== promptDraftId));
    setPromptDraftId("");
    setPromptDraftTitle("");
    setPromptDraftContent("");
  }

  function resetPrompts() {
    savePromptPresets(DEFAULT_PROMPTS);
    setPromptDraftId("");
    setPromptDraftTitle("");
    setPromptDraftContent("");
  }

  async function chatWithSelected(messageOverride?: string) {
    const messageToSend = (messageOverride ?? chatQuestion).trim();
    if (!selected || !messageToSend) return;
    setLoading("chat");
    try {
      const result = await api<ChatResponse>(`/api/announcements/${selected.id}/chat`, {
        method: "POST",
        body: JSON.stringify({ message: messageToSend }),
      });
      setChatMeta(result);
      setChatQuestion("");
      setChatPromptOpen(false);
      await loadChatHistory(selected.id);
      const detail = await api<AnnouncementDetail>(`/api/announcements/${selected.id}`);
      setSelected(detail);
      setMessage(`AI 已读取原文，长度 ${result.content_length} 字`);
      await loadOverview();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "AI 对话失败");
    } finally {
      setLoading("");
    }
  }

  async function loadChatHistory(announcementId: number) {
    const result = await api<{ items: ChatMessage[] }>(`/api/announcements/${announcementId}/chat`);
    setChatMessages(result.items);
  }

  async function refreshSelectedAnnouncement(announcementId: number) {
    const detail = await api<AnnouncementDetail>(`/api/announcements/${announcementId}`);
    setSelected(detail);
    if (detail.analysis_status === "succeeded") {
      try {
        setAnalysis(await api<Analysis>(`/api/analysis/${announcementId}`));
      } catch {
        setAnalysis(null);
      }
    }
  }

  async function selectAnnouncement(item: Announcement) {
    const detail = await api<AnnouncementDetail>(`/api/announcements/${item.id}`);
    setSelected(detail);
    setAnalysis(null);
    setChatMeta(null);
    await loadChatHistory(item.id);
    if (detail.analysis_status !== "succeeded") return;
    try {
      setAnalysis(await api<Analysis>(`/api/analysis/${item.id}`));
    } catch {
      setAnalysis(null);
    }
  }

  async function saveSettings() {
    setLoading("settings");
    try {
      await api("/api/settings/models", {
        method: "POST",
        body: JSON.stringify({
          provider: settings.provider,
          model: settings.model,
          base_url: settings.base_url || null,
          api_key: settings.api_key || null,
        }),
      });
      setMessage("模型配置已保存");
      await loadSettings();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    } finally {
      setLoading("");
    }
  }

  async function saveAnalysisPrompts(next = analysisPrompts) {
    setLoading("analysisPrompt");
    try {
      const result = await api<{ items: AnalysisPromptPreset[] }>("/api/settings/analysis-prompts", {
        method: "POST",
        body: JSON.stringify({ items: next }),
      });
      setAnalysisPrompts(result.items);
      setMessage("自动分析 Prompt 已保存");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存 Prompt 失败");
    } finally {
      setLoading("");
    }
  }

  function updateAnalysisPrompt(id: string, patch: Partial<AnalysisPromptPreset>) {
    setAnalysisPrompts((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }

  function addAnalysisPrompt() {
    const id = crypto.randomUUID();
    const source = analysisPrompts.find((item) => item.is_active) ?? analysisPrompts[0];
    const next = [
      ...analysisPrompts,
      {
        id,
        title: "新的分析 Prompt",
        system_prompt: source?.system_prompt ?? "你是一个谨慎的A股公告研究助手。请只基于公告内容输出研究分析。",
        user_instruction: source?.user_instruction ?? "请基于公告正文输出研究分析。",
        is_active: analysisPrompts.length === 0,
      },
    ];
    setAnalysisPrompts(next);
  }

  function activateAnalysisPrompt(id: string) {
    setAnalysisPrompts((current) => current.map((item) => ({ ...item, is_active: item.id === id })));
  }

  function deleteAnalysisPrompt(id: string) {
    setAnalysisPrompts((current) => {
      if (current.length <= 1) return current;
      const next = current.filter((item) => item.id !== id);
      if (!next.some((item) => item.is_active)) next[0].is_active = true;
      return next;
    });
  }

  async function cleanup(path: string, body?: object) {
    setLoading("cleanup");
    try {
      const result = await api<{ affected: number }>(path, {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      });
      setMessage(`清理完成：${result.affected} 条`);
      setSelected(null);
      setAnalysis(null);
      setChatMessages([]);
      await loadOverview();
      await loadAnnouncements();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "清理失败");
    } finally {
      setLoading("");
    }
  }

  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
  const pageIds = data.items.map((item) => item.id);
  const pageAllSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.includes(id));
  const activeAnalysisPrompt = analysisPrompts.find((item) => item.is_active);

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brandBlock">
          <h1>StockAI</h1>
        </div>
        <nav className="topNav">
          <button className={view === "workspace" ? "navActive" : ""} onClick={() => setView("workspace")}>
            <Database size={18} /> 工作台
          </button>
          <button className={view === "research" ? "navActive" : ""} onClick={() => setView("research")}>
            <FileText size={18} /> 研报翻译
          </button>
          <button className={view === "settings" ? "navActive" : ""} onClick={() => setView("settings")}>
            <Settings size={18} /> 设置
          </button>
        </nav>
      </header>

      {view === "research" ? (
        <ResearchReportsView />
      ) : view === "settings" ? (
        <section className="settingsPage">
          <div className="settingsHero">
            <div>
              <h2>设置</h2>
              <p>当前启用：{activeAnalysisPrompt?.title ?? "未加载"}</p>
            </div>
            <button className="primary" onClick={() => saveAnalysisPrompts()} disabled={loading === "analysisPrompt"}>
              {loading === "analysisPrompt" ? <Loader2 className="spin" size={18} /> : <Save size={18} />} 保存 Prompt
            </button>
          </div>

          <section className="settingsPane modelSettings">
            <h3>模型配置</h3>
            <div className="settingsGrid">
              <label>
                Provider
                <select value={settings.provider} onChange={(event) => setSettings({ ...settings, provider: event.target.value as ModelSettingsState["provider"] })}>
                  <option value="mock">mock/free-test</option>
                  <option value="openai">OpenAI API</option>
                  <option value="openai-compatible">OpenAI-compatible</option>
                </select>
              </label>
              <label>
                Model
                <input value={settings.model} onChange={(event) => setSettings({ ...settings, model: event.target.value })} />
              </label>
              <label>
                Base URL
                <input value={settings.base_url} onChange={(event) => setSettings({ ...settings, base_url: event.target.value })} placeholder="http://127.0.0.1:11434/v1" />
              </label>
              <label>
                API Key
                <input value={settings.api_key} onChange={(event) => setSettings({ ...settings, api_key: event.target.value })} type="password" placeholder={settings.has_api_key ? "已保存，留空将清除" : "mock 可留空"} />
              </label>
            </div>
            <button className="primary" onClick={saveSettings} disabled={loading === "settings"}>
              {loading === "settings" ? <Loader2 className="spin" size={18} /> : <Save size={18} />} 保存模型
            </button>
          </section>

          <section className="settingsPane promptSettings">
            <div className="sectionHead">
              <h3>自动分析 Prompt</h3>
              <button onClick={addAnalysisPrompt}>
                <Plus size={17} /> 新增
              </button>
            </div>
            <div className="promptEditorGrid">
              {analysisPrompts.map((prompt) => (
                <article className={`promptEditor ${prompt.is_active ? "activePrompt" : ""}`} key={prompt.id}>
                  <div className="promptEditorHead">
                    <input value={prompt.title} onChange={(event) => updateAnalysisPrompt(prompt.id, { title: event.target.value })} />
                    <button className={prompt.is_active ? "primary" : ""} onClick={() => activateAnalysisPrompt(prompt.id)}>
                      {prompt.is_active ? "已启用" : "启用"}
                    </button>
                    <button onClick={() => deleteAnalysisPrompt(prompt.id)} disabled={analysisPrompts.length <= 1}>
                      <Trash2 size={16} />
                    </button>
                  </div>
                  <label>
                    System Prompt
                    <textarea value={prompt.system_prompt} onChange={(event) => updateAnalysisPrompt(prompt.id, { system_prompt: event.target.value })} rows={4} />
                  </label>
                  <label>
                    User Instruction
                    <textarea value={prompt.user_instruction} onChange={(event) => updateAnalysisPrompt(prompt.id, { user_instruction: event.target.value })} rows={5} />
                  </label>
                </article>
              ))}
            </div>
          </section>
        </section>
      ) : (
        <>
          <section className="workflowBar">
            <label>
              <CalendarDays size={17} />
              <input type="date" value={ymdToDateInput(date)} onChange={(event) => setDate(dateInputToYmd(event.target.value))} />
            </label>
            <button onClick={fetchAnnouncements} disabled={loading === "fetch"}>
              {loading === "fetch" ? <Loader2 className="spin" size={18} /> : <RefreshCw size={18} />} 抓取并初筛
            </button>
            <button onClick={screenAnnouncements} disabled={loading === "screen"}>
              {loading === "screen" ? <Loader2 className="spin" size={18} /> : <Brain size={18} />} 重新初筛
            </button>
            {analysisJob?.running ? (
              <button onClick={cancelAutoAnalysis} disabled={loading === "cancelAnalyze"}>
                {loading === "cancelAnalyze" ? <Loader2 className="spin" size={18} /> : <Square size={18} />} 取消分析
              </button>
            ) : (
              <button onClick={startAutoAnalysis} disabled={loading === "autoAnalyze"}>
                {loading === "autoAnalyze" ? <Loader2 className="spin" size={18} /> : <Play size={18} />} {selectedIds.length ? `分析已选 ${selectedIds.length}` : "自动分析"}
              </button>
            )}
            <label className="search">
              <Search size={17} />
              <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="代码、名称、标题" />
            </label>
            <select value={announcementType} onChange={(event) => setAnnouncementType(event.target.value)}>
              <option value="">全部类型</option>
              {filterOptions.announcement_types.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <label className="check">
              <input type="checkbox" checked={aiOnly} onChange={(event) => setAiOnly(event.target.checked)} />
              只看AI关注
            </label>
          </section>

          <section className="databaseBar">
            <div>
              <Database size={18} />
              <span>公告 {summary?.total_announcements ?? 0}</span>
              <span>AI关注 {summary?.ai_tracking_announcements ?? 0}</span>
              <span>已分析 {summary?.analyzed_announcements ?? 0}</span>
              <span>原文 {summary?.content_announcements ?? 0}</span>
              <span>对话 {summary?.chat_messages ?? 0}</span>
              <span>任务 {analysisJob?.message || "空闲"} {analysisJob?.requested ? `${analysisJob.analyzed}/${analysisJob.requested}` : ""}</span>
            </div>
            <button onClick={() => cleanup("/api/database/cleanup/untracked", { date })} disabled={loading === "cleanup"}>
              <Trash2 size={16} /> 删未关注
            </button>
            <button onClick={() => cleanup("/api/database/cleanup/content")} disabled={loading === "cleanup"}>
              <Trash2 size={16} /> 清原文
            </button>
            <button onClick={() => cleanup("/api/database/cleanup/old", { days: 3 })} disabled={loading === "cleanup"}>
              <Trash2 size={16} /> 删3天前
            </button>
            <button onClick={() => cleanup("/api/database/cleanup/all")} disabled={loading === "cleanup"}>
              <Trash2 size={16} /> 清空库
            </button>
          </section>

          <section className="workspace">
            <div className="tablePane">
              <div className="summaryLine">
                <span>{data.total} 条公告</span>
                <span>第 {page} / {totalPages} 页</span>
              </div>
              <div className="table">
                <div className="row head">
                  <span><input type="checkbox" checked={pageAllSelected} onChange={(event) => togglePageSelection(event.target.checked)} /></span>
                  <span>代码</span>
                  <span>名称</span>
                  <span>标题</span>
                  <span>类型</span>
                  <span>分析</span>
                  <span>操作</span>
                </div>
                {data.items.map((item) => (
                  <div className={`row item ${selected?.id === item.id ? "selected" : ""}`} key={item.id}>
                    <span><input type="checkbox" checked={selectedIds.includes(item.id)} onChange={(event) => toggleSelectedId(item.id, event.target.checked)} /></span>
                    <span>{item.code}</span>
                    <span>{item.name}</span>
                    <button type="button" className="titleButton" onClick={() => selectAnnouncement(item)}>{item.title}</button>
                    <span>{item.announcement_type}</span>
                    <span className={`pill ${item.analysis_status}`}>{item.analysis_status}</span>
                    <button type="button" onClick={() => analyzeOne(item)} disabled={loading === `analyze-${item.id}`}>
                      {loading === `analyze-${item.id}` ? <Loader2 className="spin" size={16} /> : <Play size={16} />} 分析
                    </button>
                  </div>
                ))}
              </div>
              <div className="pager">
                <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1}><ChevronLeft size={18} /></button>
                <button onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page >= totalPages}><ChevronRight size={18} /></button>
              </div>
            </div>

            <aside className="detailPane">
              {selected ? (
                <>
                  <div className="detailHead">
                    <div>
                      <h2>{selected.name} {selected.code}</h2>
                      <p>{selected.announcement_date} · {selected.announcement_type}</p>
                    </div>
                    <button type="button" onClick={() => analyzeOne(selected)} disabled={loading === `analyze-${selected.id}`}>
                      {loading === `analyze-${selected.id}` ? <Loader2 className="spin" size={16} /> : <Play size={16} />} 分析
                    </button>
                  </div>
                  <h3>{selected.title}</h3>
                  <div className="tags">
                    {selected.ai_worth_tracking && <span className="tag important">AI关注 {selected.ai_importance_score}</span>}
                    {selected.ai_event_type && <span className="tag">{selected.ai_event_type}</span>}
                    <span className="tag">分析：{selected.analysis_status}</span>
                    {selected.matched_keywords.map((item) => <span className="tag" key={item}>{item}</span>)}
                  </div>
                  {selected.ai_screen_reason && <p className="screenReason">{selected.ai_screen_reason}</p>}
                  <a href={selected.url} target="_blank" rel="noreferrer">打开公告原文</a>
                  <div className="statusLine">
                    <span>原文：{selected.content_length || 0} 字</span>
                    <span>解析状态：{selected.parse_status}</span>
                  </div>
                  {analysis ? <AnalysisView analysis={analysis} /> : <p className="empty">分析完成后会显示模型输出。</p>}

                  <section className="chatBox">
                    <div className="chatHeader">
                      <h4><MessageSquare size={16} /> 和AI对话</h4>
                      <button type="button" onClick={() => setChatPromptOpen(true)}>
                        <Settings size={15} /> 快捷Prompt
                      </button>
                    </div>
                    <div className="chatMessages">
                      {chatMessages.length === 0 && <p className="empty">还没有对话。</p>}
                      {chatMessages.map((item) => (
                        <div className={`chatMessage ${item.role}`} key={item.id}>
                          <strong>{item.role === "assistant" ? "AI" : "你"}</strong>
                          <p>{item.content}</p>
                        </div>
                      ))}
                    </div>
                    <textarea value={chatQuestion} onChange={(event) => setChatQuestion(event.target.value)} rows={3} />
                    <button className="primary" onClick={() => chatWithSelected()} disabled={loading === "chat"}>
                      {loading === "chat" ? <Loader2 className="spin" size={18} /> : <MessageSquare size={18} />} 发送
                    </button>
                    {chatMeta && (
                      <details className="chatEvidence">
                        <summary>{chatMeta.provider} / {chatMeta.model} · 原文 {chatMeta.content_length} 字</summary>
                        <pre>{chatMeta.content_preview}</pre>
                      </details>
                    )}
                  </section>
                </>
              ) : (
                <p className="empty">选择一条公告查看详情。</p>
              )}
            </aside>
          </section>
        </>
      )}

      {chatPromptOpen && (
        <div className="modalLayer" role="dialog" aria-modal="true">
          <div className="promptModal">
            <div className="modalHead">
              <h3>AI 对话 Prompt</h3>
              <button onClick={() => setChatPromptOpen(false)}><X size={18} /></button>
            </div>
            <div className="promptQuickList">
              {promptPresets.map((prompt) => (
                <div className="promptItem" key={prompt.id}>
                  <button type="button" onClick={() => chatWithSelected(prompt.content)}>{prompt.title}</button>
                  <button type="button" onClick={() => editPrompt(prompt)}>编辑</button>
                </div>
              ))}
            </div>
            <label>
              名称
              <input value={promptDraftTitle} onChange={(event) => setPromptDraftTitle(event.target.value)} placeholder="例如：核查财务影响" />
            </label>
            <label>
              内容
              <textarea value={promptDraftContent} onChange={(event) => setPromptDraftContent(event.target.value)} rows={5} placeholder="输入要发送给 AI 的问题模板" />
            </label>
            <div className="promptActions">
              <button type="button" onClick={savePromptDraft}><Save size={15} /> 保存</button>
              <button type="button" onClick={deletePromptDraft} disabled={!promptDraftId}><Trash2 size={15} /> 删除</button>
              <button type="button" onClick={resetPrompts}><RefreshCw size={15} /> 默认</button>
            </div>
          </div>
        </div>
      )}

      {message && <div className="toast">{message}</div>}
    </main>
  );
}

function AnalysisView({ analysis }: { analysis: Analysis }) {
  const output = analysis.free_output || analysis.summary;
  return (
    <div className="analysis">
      <div className="scoreLine">
        <span>自由输出</span>
        <span>{analysis.provider} / {analysis.model}</span>
      </div>
      <pre className="freeOutput">{output}</pre>
    </div>
  );
}

function ResearchReportsView() {
  const [reports, setReports] = useState<ResearchReportResponse>({ items: [], total: 0 });
  const [selected, setSelected] = useState<ResearchReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState("");
  const [error, setError] = useState("");
  const [job, setJob] = useState<AnalysisJobStatus | null>(null);

  async function selectReport(report: ResearchReportSummary) {
    setError("");
    try {
      setSelected(await api<ResearchReportDetail>(`/api/research-reports/${report.id}`));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "研报加载失败");
    }
  }

  async function loadReports(selectFirst = false) {
    setLoading(true);
    setError("");
    try {
      const result = await api<ResearchReportResponse>("/api/research-reports");
      setReports(result);
      const current = selected && result.items.find((item) => item.id === selected.id);
      if (current) await selectReport(current);
      else if (selectFirst && result.items.length) await selectReport(result.items[0]);
      else if (!result.items.length) setSelected(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "研报列表加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function deleteReport(report: ResearchReportSummary) {
    if (!window.confirm(`确定删除“${report.report_name}”吗？数据库中的记录也会被删除。`)) return;
    setAction(`delete-${report.id}`);
    try {
      await api(`/api/research-reports/${report.id}`, { method: "DELETE" });
      if (selected?.id === report.id) setSelected(null);
      await loadReports(true);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "删除失败");
    } finally {
      setAction("");
    }
  }

  async function clearReports() {
    if (!window.confirm("确定删除全部研报吗？此操作会清空数据库中的全部研报记录。")) return;
    setAction("clear");
    try {
      await api("/api/research-reports", { method: "DELETE" });
      setSelected(null);
      await loadReports();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "清空失败");
    } finally {
      setAction("");
    }
  }

  async function analyzeReport(report: ResearchReportSummary) {
    setAction(`analyze-${report.id}`);
    setError("");
    try {
      const result = await api<ResearchReportDetail>(`/api/research-reports/${report.id}/analyze`, { method: "POST" });
      setSelected(result);
      await loadReports();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AI 分析失败");
    } finally {
      setAction("");
    }
  }

  async function startAutoAnalysis() {
    setAction("auto");
    try {
      setJob(await api<AnalysisJobStatus>("/api/research-reports/analysis/auto/start", {
        method: "POST",
        body: JSON.stringify({ limit: Math.max(reports.total, 1) }),
      }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "自动分析启动失败");
    } finally {
      setAction("");
    }
  }

  async function cancelAutoAnalysis() {
    setJob(await api<AnalysisJobStatus>("/api/research-reports/analysis/auto/cancel", { method: "POST" }));
  }

  useEffect(() => {
    async function initializeReports() {
      try {
        await loadReports(true);
        setJob(await api<AnalysisJobStatus>("/api/research-reports/analysis/auto/status"));
      } catch { /* loadReports already exposes request errors */ }
    }
    initializeReports();
  }, []);

  useEffect(() => {
    if (!job?.running) return;
    const timer = window.setInterval(async () => {
      const status = await api<AnalysisJobStatus>("/api/research-reports/analysis/auto/status");
      setJob(status);
      await loadReports();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [job?.running]);

  return (
    <section className="researchPage">
      <header className="researchHero">
        <div>
          <span className="researchEyebrow">TRANSLATED RESEARCH ARCHIVE</span>
          <h2>研报翻译</h2>
          <p>浏览自动抓取并翻译的研究报告，共 {reports.total} 篇。</p>
        </div>
        <div className="researchActions">
          <button onClick={() => loadReports(true)} disabled={loading}><RefreshCw className={loading ? "spin" : ""} size={17} /> 加载数据</button>
          {job?.running ? (
            <button onClick={cancelAutoAnalysis}><Square size={17} /> 取消分析</button>
          ) : (
            <button className="primary" onClick={startAutoAnalysis} disabled={!reports.total || action === "auto"}>
              {action === "auto" ? <Loader2 className="spin" size={17} /> : <Brain size={17} />} 自动分析
            </button>
          )}
          <button onClick={clearReports} disabled={!reports.total || action === "clear" || job?.running}><Trash2 size={17} /> 清空全部</button>
        </div>
      </header>

      {job?.message && <div className="researchJob">{job.message}{job.requested ? ` · ${job.analyzed}/${job.requested}，失败 ${job.failed}` : ""}</div>}

      {error && <div className="researchError">{error}</div>}
      <div className="researchWorkspace">
        <aside className="reportShelf" aria-label="研报列表">
          <div className="reportShelfHead">
            <strong>报告目录</strong>
            <span>{reports.total}</span>
          </div>
          {loading && <p className="empty">正在载入研报…</p>}
          {!loading && reports.items.length === 0 && <p className="empty">尚未收到研报数据。</p>}
          {reports.items.map((report, index) => (
            <div className={`reportShelfItem ${selected?.id === report.id ? "selected" : ""}`} key={report.id}>
              <button type="button" className="reportSelect" onClick={() => selectReport(report)}>
                <span className="reportIndex">{String(index + 1).padStart(2, "0")}</span>
                <span className="reportShelfCopy">
                  <strong>{report.report_name}</strong>
                  <small>{report.source} · {formatReportDate(report.updated_at)} · {report.analysis_status}</small>
                </span>
              </button>
              <div className="reportItemActions">
                <button title="AI 分析" onClick={() => analyzeReport(report)} disabled={action === `analyze-${report.id}`}><Brain size={14} /></button>
                <button title="删除" onClick={() => deleteReport(report)} disabled={action === `delete-${report.id}` || job?.running}><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </aside>

        <article className="reportReader">
          {selected ? (
            <>
              <header className="reportReaderHead">
                <div>
                  <span>{selected.source}</span>
                  <h3>{selected.report_name}</h3>
                </div>
                <time>{formatReportDate(selected.updated_at)}</time>
              </header>
              <div className="translatedText">{selected.translated_text}</div>
              <section className="reportAnalysis">
                <div className="reportAnalysisHead">
                  <h4>AI 分析</h4>
                  <button onClick={() => analyzeReport(selected)} disabled={action === `analyze-${selected.id}`}>
                    {action === `analyze-${selected.id}` ? <Loader2 className="spin" size={16} /> : <Brain size={16} />} 分析这篇研报
                  </button>
                </div>
                {selected.analysis_output ? (
                  <>
                    <small>{selected.analysis_provider} / {selected.analysis_model}</small>
                    <div className="analysisOutput">{selected.analysis_output}</div>
                  </>
                ) : <p className="empty">状态：{selected.analysis_status}。分析完成后结果会显示在这里。</p>}
                {selected.analysis_error && <p className="researchError">{selected.analysis_error}</p>}
              </section>
            </>
          ) : (
            !loading && <div className="reportEmpty"><FileText size={34} /><p>从左侧选择一篇研报开始阅读。</p></div>
          )}
        </article>
      </div>
    </section>
  );
}

function formatReportDate(value: string) {
  const normalized = value.includes("T") ? value : `${value.replace(" ", "T")}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" });
}

createRoot(document.getElementById("root")!).render(<App />);
