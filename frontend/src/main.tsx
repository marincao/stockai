import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Brain,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Database,
  Loader2,
  MessageSquare,
  Play,
  RefreshCw,
  Save,
  Search,
  Settings,
  Square,
  Trash2,
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

function todayYmd() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
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
  const [promptPresets, setPromptPresets] = useState<PromptPreset[]>(loadPromptPresets);
  const [promptDraftId, setPromptDraftId] = useState("");
  const [promptDraftTitle, setPromptDraftTitle] = useState("");
  const [promptDraftContent, setPromptDraftContent] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<ModelSettingsState>({
    provider: "mock",
    model: "mock-free-test",
    base_url: "",
    api_key: "",
  });
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

  async function loadAnalysisJob() {
    setAnalysisJob(await api<AnalysisJobStatus>("/api/analysis/auto/status"));
  }

  useEffect(() => {
    loadAnnouncements().catch((error) => setMessage(error.message));
  }, [query]);

  useEffect(() => {
    loadOverview().catch((error) => setMessage(error.message));
    loadSettings().catch((error) => setMessage(error.message));
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
      const limit = Math.min(Math.max(summary?.ai_tracking_announcements ?? 500, 500), 5000);
      const result = await api<AnalysisJobStatus>("/api/analysis/auto/start", {
        method: "POST",
        body: JSON.stringify({ date, limit }),
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

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <h1>StockAI</h1>
          <p>临时公告工作台：保留最近 3 天，后台分析 AI 关注公告</p>
        </div>
        <button onClick={() => setSettingsOpen(!settingsOpen)} title="模型设置">
          <Settings size={18} /> 模型
        </button>
      </header>

      {settingsOpen && (
        <section className="settingsPane compactSettings">
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
          <button className="primary" onClick={saveSettings} disabled={loading === "settings"} title="保存模型配置">
            {loading === "settings" ? <Loader2 className="spin" size={18} /> : <Save size={18} />} 保存
          </button>
        </section>
      )}

      <section className="workflowBar">
        <label>
          <CalendarDays size={17} />
          <input value={date} onChange={(event) => setDate(event.target.value)} maxLength={8} />
        </label>
        <button onClick={fetchAnnouncements} disabled={loading === "fetch"} title="抓取公告并同步初筛">
          {loading === "fetch" ? <Loader2 className="spin" size={18} /> : <RefreshCw size={18} />} 抓取并初筛
        </button>
        <button onClick={screenAnnouncements} disabled={loading === "screen"} title="按当前规则重新初筛当前日期">
          {loading === "screen" ? <Loader2 className="spin" size={18} /> : <Brain size={18} />} 重新初筛
        </button>
        {analysisJob?.running ? (
          <button onClick={cancelAutoAnalysis} disabled={loading === "cancelAnalyze"} title="取消后台自动分析">
            {loading === "cancelAnalyze" ? <Loader2 className="spin" size={18} /> : <Square size={18} />} 取消分析
          </button>
        ) : (
          <button onClick={startAutoAnalysis} disabled={loading === "autoAnalyze"} title="后台分析所有AI关注公告">
            {loading === "autoAnalyze" ? <Loader2 className="spin" size={18} /> : <Play size={18} />} 自动分析
          </button>
        )}
        <label className="search">
          <Search size={17} />
          <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="代码、名称、标题" />
        </label>
        <select value={announcementType} onChange={(event) => setAnnouncementType(event.target.value)} title="公告类型">
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
          <span>存原文 {summary?.content_announcements ?? 0}</span>
          <span>对话 {summary?.chat_messages ?? 0}</span>
          <span>任务 {analysisJob?.message || "空闲"} {analysisJob?.requested ? `${analysisJob.analyzed}/${analysisJob.requested}` : ""}</span>
        </div>
        <button onClick={() => cleanup("/api/database/cleanup/untracked", { date })} disabled={loading === "cleanup"} title="删除当前日期未被AI关注的公告">
          <Trash2 size={16} /> 删未关注
        </button>
        <button onClick={() => cleanup("/api/database/cleanup/content")} disabled={loading === "cleanup"} title="清空已分析公告原文">
          <Trash2 size={16} /> 清原文
        </button>
        <button onClick={() => cleanup("/api/database/cleanup/old", { days: 3 })} disabled={loading === "cleanup"} title="删除3天前公告">
          <Trash2 size={16} /> 删3天前
        </button>
        <button onClick={() => cleanup("/api/database/cleanup/all")} disabled={loading === "cleanup"} title="清空全部公告、分析和对话">
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
              <span>代码</span>
              <span>名称</span>
              <span>标题</span>
              <span>类型</span>
              <span>分析</span>
            </div>
            {data.items.map((item) => (
              <button className={`row item ${selected?.id === item.id ? "selected" : ""}`} key={item.id} onClick={() => selectAnnouncement(item)}>
                <span>{item.code}</span>
                <span>{item.name}</span>
                <span className="titleText">{item.title}</span>
                <span>{item.announcement_type}</span>
                <span className={`pill ${item.analysis_status}`}>{item.analysis_status}</span>
              </button>
            ))}
          </div>
          <div className="pager">
            <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1} title="上一页">
              <ChevronLeft size={18} />
            </button>
            <button onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page >= totalPages} title="下一页">
              <ChevronRight size={18} />
            </button>
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
              {analysis ? <AnalysisView analysis={analysis} /> : <p className="empty">自动分析完成后，这里会显示摘要、行动建议、风险提示和待验证线索。</p>}

              <section className="chatBox">
                <div className="chatHeader">
                  <h4><MessageSquare size={16} /> 和AI对话</h4>
                  <details className="promptMenu">
                    <summary><Settings size={15} /> 快捷Prompt</summary>
                    <div className="promptPanel">
                      <div className="promptQuickList">
                        {promptPresets.map((prompt) => (
                          <div className="promptItem" key={prompt.id}>
                            <button type="button" onClick={() => chatWithSelected(prompt.content)} title="直接发送这个 Prompt">
                              {prompt.title}
                            </button>
                            <button type="button" onClick={() => editPrompt(prompt)} title="编辑这个 Prompt">
                              编辑
                            </button>
                          </div>
                        ))}
                      </div>
                      <label>
                        名称
                        <input value={promptDraftTitle} onChange={(event) => setPromptDraftTitle(event.target.value)} placeholder="例如：核查财务影响" />
                      </label>
                      <label>
                        内容
                        <textarea value={promptDraftContent} onChange={(event) => setPromptDraftContent(event.target.value)} rows={4} placeholder="输入要发送给 AI 的问题模板" />
                      </label>
                      <div className="promptActions">
                        <button type="button" onClick={savePromptDraft}><Save size={15} /> 保存</button>
                        <button type="button" onClick={deletePromptDraft} disabled={!promptDraftId}><Trash2 size={15} /> 删除</button>
                        <button type="button" onClick={resetPrompts}><RefreshCw size={15} /> 默认</button>
                      </div>
                    </div>
                  </details>
                </div>
                <div className="chatMessages">
                  {chatMessages.length === 0 && <p className="empty">还没有对话。第一次提问会先读取公告原文。</p>}
                  {chatMessages.map((item) => (
                    <div className={`chatMessage ${item.role}`} key={item.id}>
                      <strong>{item.role === "assistant" ? "AI" : "你"}</strong>
                      <p>{item.content}</p>
                    </div>
                  ))}
                </div>
                <textarea value={chatQuestion} onChange={(event) => setChatQuestion(event.target.value)} rows={3} />
                <button className="primary" onClick={() => chatWithSelected()} disabled={loading === "chat"} title="发送问题">
                  {loading === "chat" ? <Loader2 className="spin" size={18} /> : <MessageSquare size={18} />}
                  发送
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

      {message && <div className="toast">{message}</div>}
    </main>
  );
}

function AnalysisView({ analysis }: { analysis: Analysis }) {
  return (
    <div className="analysis">
      <div className="scoreLine">
        <span className={`sentiment ${analysis.sentiment}`}>{analysis.sentiment}</span>
        <span>重要性 {analysis.importance_score}</span>
        <span>置信度 {Math.round(analysis.confidence * 100)}%</span>
      </div>
      <p>{analysis.summary}</p>
      {analysis.action_suggestion && <p className="actionSuggestion">{analysis.action_suggestion}</p>}
      <List title="风险提示" items={analysis.risk_points} />
      <List title="待验证假设" items={analysis.opportunities} />
      <List title="下一步观察" items={analysis.watch_signals} />
      <p className="reason">{analysis.reasoning_short}</p>
      <p className="disclaimer">{analysis.not_investment_advice}</p>
    </div>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="listBlock">
      <h4>{title}</h4>
      <ul>
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </section>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
