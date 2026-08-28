'use client';

/**
 * 全局 AI 悬浮助手：所有页面右下角悬浮按钮 → 点击弹开对话窗。
 * - 按当前页面注入上下文（论文详情 / 趋势 / 选题 / 检索 / 工作台 …），回答贴合页面。
 * - 会话管理：自动创建会话并保存历史记录，支持历史列表 / 加载 / 删除。
 * - 支持最大化（放大）。
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { usePathname } from 'next/navigation';
import { X, Maximize2, Minimize2, Send, Square, Sparkles, History, Plus, Trash2, Search, Download, ChevronDown, Brain, Bookmark, Mic, MicOff } from 'lucide-react';
import ChatMessageList, { ChatMessageItem, ChatToolsEvent, ChatToolProgress, downloadChatMarkdown } from './ChatMessageList';
import { assistantApi, papersApi, personalApi, getLastModel, rememberModel, AssistantSession } from '@/lib/api';
import { getUserId } from '@/lib/user';
import { useBookmarks } from '@/lib/useBookmarks';
import { useToast } from '@/components/Toast';

// —— AI 追问同款直连后端 SSE（绕过 Next dev 代理 gzip 缓冲，保证浏览器真正逐字流式）——
const ASSISTANT_BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
const ASSISTANT_API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || '';

function assistantHeaders(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (ASSISTANT_API_TOKEN) h['x-api-token'] = ASSISTANT_API_TOKEN;
  // 会话按用户隔离（后端 _load_session 校验 user_id），必须带与创建会话一致的 x-user-id
  try {
    h['x-user-id'] = getUserId();
  } catch { /* SSR 环境忽略 */ }
  return h;
}

interface AssistantStreamEvent {
  content?: string;
  reasoning?: string;
  tool_progress?: { tool: string; args?: Record<string, unknown> };
  tools?: unknown[];
  error?: string;
  done?: boolean;
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
}

/** 直连后端 POST /assistant/chat 的 SSE 流式读取（逐帧解析 content/reasoning/tool_progress/tools/usage/error/done）。 */
async function streamAssistantDirect(
  sessionId: number,
  messages: Array<{ role: string; content: string }>,
  onEvent: (ev: AssistantStreamEvent) => void,
  signal?: AbortSignal,
  agentEnabled?: boolean,
  model?: string,
): Promise<void> {
  const body: Record<string, unknown> = { messages, session_id: sessionId };
  if (agentEnabled !== undefined) body.agent_enabled = agentEnabled;
  if (model) body.model = model;
  const res = await fetch(`${ASSISTANT_BACKEND_URL}/api/assistant/chat`, {
    method: 'POST',
    headers: assistantHeaders(),
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err: unknown = await res.json();
      if (err && typeof err === 'object' && typeof (err as { detail?: unknown }).detail === 'string') {
        detail = (err as { detail: string }).detail;
      }
    } catch { /* 忽略解析失败 */ }
    onEvent({ error: detail });
    return;
  }
  if (!res.body) {
    onEvent({ error: '响应无内容' });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let data: Record<string, unknown>;
        try {
          data = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
        if (data.error) {
          onEvent({ error: String(data.error) });
          return;
        }
        if (data.done) {
          onEvent({ done: true });
          return;
        }
        if (typeof data.content === 'string' && data.content) onEvent({ content: data.content });
        else if (typeof data.reasoning === 'string' && data.reasoning) onEvent({ reasoning: data.reasoning });
        else if (data.tool_progress && typeof data.tool_progress === 'object') {
          onEvent({ tool_progress: data.tool_progress as { tool: string; args?: Record<string, unknown> } });
        } else if (Array.isArray(data.tools)) {
          onEvent({ tools: data.tools as unknown[] });
        } else if (data.usage && typeof data.usage === 'object') {
          onEvent({ usage: data.usage as { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } });
        }
      }
    }
  } catch (e: unknown) {
    if ((e as Error).name !== 'AbortError') throw e;
    return;
  }
  onEvent({ done: true });
}

// 简单内容哈希(djb2)→ hex,用于 AI 反馈按答案去重
function hashString(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h.toString(16);
}

const PAGE_LABELS: Record<string, string> = {
  paper: '论文助手',
  trends: '趋势助手',
  topics: '选题助手',
  search: '检索助手',
  dashboard: '工作台助手',
  network: '网络助手',
  reading: '阅读助手',
  home: 'AI 助手',
  generic: 'AI 助手',
};

// 子 tab 专属助手名（展示标题更精确）
const TAB_LABELS: Record<string, string> = {
  'dashboard:workbench': '今日值得读助手',
  'dashboard:briefing': '领域快讯助手',
  'dashboard:stack': '我的研究栈助手',
  'dashboard:prefs': '推荐偏好助手',
  'topics:list': '研究工作台助手',
  'topics:project': '研究项目助手',
  'topics:step1': '选题定义助手',
  'topics:step2': '选题验证助手',
  'topics:step3': '文献管理助手',
  'topics:step4': '数据方法助手',
  'topics:step5': '写作输出助手',
};

// 子 tab 描述（注入上下文，帮助 AI 理解当前子页面）
const TAB_DESCRIPTIONS: Record<string, string> = {
  'dashboard:workbench': '正在研究工作台的「今日值得读」推荐列表',
  'dashboard:briefing': '正在查看工作台的「领域快讯」热点趋势',
  'dashboard:stack': '正在查看工作台的「我的研究栈」',
  'dashboard:prefs': '正在设置工作台的「推荐偏好」',
  'topics:list': '正在研究工作台的项目列表页（灵感区 + 我的研究项目）',
  'topics:project': '正在查看一个研究项目',
  'topics:step1': '正在研究项目的「选题定义」步骤（打磨题目与研究问题）',
  'topics:step2': '正在研究项目的「选题验证」步骤（新颖性/拥挤度/竞争）',
  'topics:step3': '正在研究项目的「文献管理」步骤（收集与精读相关论文）',
  'topics:step4': '正在研究项目的「数据与方法」步骤（数据来源与识别策略）',
  'topics:step5': '正在研究项目的「写作输出」步骤（综述/立项书/期刊）',
};

// 预设问题：页面级 + 子 tab 级，每个 2-3 个，点击直接发送
const SUGGESTIONS: Record<string, string[]> = {
  paper: ['这篇论文的核心贡献是什么？', '帮我总结它的研究方法', '它的结论有什么不足？'],
  trends: ['最近的研究热点是什么？', '这个方向有哪些研究空白？', '帮我解读趋势数据'],
  search: ['帮我优化检索词', '这些结果里哪篇最值得读？', '总结一下检索到的文献'],
  network: ['这个网络揭示了什么结构？', '哪些节点是核心？'],
  reading: ['我最近在看什么方向？', '帮我总结最近的阅读'],
  home: ['今天有什么值得读的论文？', '最近哪些领域在升温？', '有什么新的研究动态？'],
  generic: ['帮我解读当前页面'],
  'dashboard:workbench': ['今天有哪些值得读的论文？', '今天的推荐依据是什么？', '帮我解读今日推荐'],
  'dashboard:briefing': ['最近的研究热点是什么？', '这些热点有什么研究空白？', '热点趋势说明了什么？'],
  'dashboard:stack': ['我的研究进展如何？', '我最近关注了哪些方向？', '帮我梳理我的研究脉络'],
  'dashboard:prefs': ['如何设置推荐偏好？', '关注哪些子领域更合适？'],
  'topics:list': ['怎么从研究空白里找选题？', '我该关注哪些方向？', '帮我评估一个研究想法'],
  'topics:project': ['这个项目下一步该做什么？', '帮我看看这个选题有什么风险'],
  'topics:step1': ['帮我把这个想法打磨成具体选题', '这个方向有哪些值得研究的问题？'],
  'topics:step2': ['这个选题是否拥挤？', '帮我解读验证报告'],
  'topics:step3': ['我的文献集覆盖够吗？', '帮我梳理文献脉络'],
  'topics:step4': ['这个选题用什么数据？', '推荐什么研究方法'],
  'topics:step5': ['我的综述有什么不足？', '这个选题适合投哪个期刊？'],
};

interface AssistantContext {
  key: string;
  page: string;
  tab?: string;
  paperId?: string;
  contextText?: string;
}

function useAssistantContext(): AssistantContext {
  const pathname = usePathname();
  const [search, setSearch] = useState('');
  useEffect(() => {
    setSearch(typeof window !== 'undefined' ? window.location.search : '');
  }, [pathname]);

  const params = new URLSearchParams(search);
  const paperMatch = /^\/paper\/([^/]+)/.exec(pathname || '');
  let page = 'generic';
  let tab: string | undefined;
  let paperId: string | undefined;
  let contextText: string | undefined;

  if (paperMatch) {
    page = 'paper';
    paperId = decodeURIComponent(paperMatch[1]);
  } else if (pathname?.startsWith('/trends')) {
    page = 'trends';
  } else if (pathname?.startsWith('/topics')) {
    page = 'topics';
    const project = params.get('project');
    if (project && /^\d+$/.test(project)) {
      const step = params.get('step');
      tab = step && /^[1-5]$/.test(step) ? `step${step}` : 'project';
    } else {
      tab = 'list';
    }
    const desc = TAB_DESCRIPTIONS[`topics:${tab}`];
    if (desc) contextText = desc;
  } else if (pathname?.startsWith('/search')) {
    page = 'search';
    const q = params.get('search') || params.get('q') || '';
    if (q) contextText = `当前检索词：${q}`;
  } else if (pathname?.startsWith('/dashboard')) {
    page = 'dashboard';
    tab = params.get('tab') || 'workbench';
    const desc = TAB_DESCRIPTIONS[`dashboard:${tab}`];
    if (desc) contextText = desc;
  } else if (pathname?.startsWith('/network')) {
    page = 'network';
  } else if (pathname?.startsWith('/reading')) {
    page = 'reading';
  } else if (pathname === '/' || !pathname) {
    page = 'home';
  }

  const key = `${page}:${tab || ''}:${paperId || ''}:${contextText || ''}`;
  return { key, page, tab, paperId, contextText };
}

export default function AIAssistant() {
  const derivedCtx = useAssistantContext();
  // 外部打开时（如论文卡片「AI 分析」）注入的上下文覆盖，页面跳转后自动清除
  const [override, setOverride] = useState<{ paperId?: string; contextText?: string } | null>(null);
  // 页面内部子 tab（工作台/选题中心通过 reportPageContext 上报）
  const [pageTab, setPageTab] = useState<string | undefined>(undefined);
  // 研究工作台项目标题（上报自 ProjectDetail，注入助手上下文）
  const [pageProjectTitle, setPageProjectTitle] = useState<string | undefined>(undefined);

  // 页面跳转时清除外部覆盖与 tab 上报
  useEffect(() => {
    setOverride(null);
    setPageTab(undefined);
    setPageProjectTitle(undefined);
  }, [derivedCtx.key]);

  // 监听页面内部子 tab 切换
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (((e as CustomEvent).detail || {})) as { tab?: string; projectTitle?: string };
      setPageTab(detail.tab || undefined);
      setPageProjectTitle(detail.projectTitle || undefined);
    };
    window.addEventListener('pp:page-context', handler);
    return () => window.removeEventListener('pp:page-context', handler);
  }, []);

  // 有效上下文：外部论文覆盖 > 页面派生 + 内部 tab
  const ctx: AssistantContext = (() => {
    if (override?.paperId) {
      return { key: `paper:${override.paperId}`, page: 'paper', paperId: override.paperId, contextText: override.contextText };
    }
    const tab = pageTab || derivedCtx.tab;
    const baseContext = TAB_DESCRIPTIONS[`${derivedCtx.page}:${tab}`] || derivedCtx.contextText;
    const contextText = pageProjectTitle ? `${baseContext || ''}。当前研究项目：${pageProjectTitle}` : baseContext;
    return {
      ...derivedCtx,
      tab,
      contextText,
      key: `${derivedCtx.page}:${tab || ''}:${derivedCtx.paperId || ''}:${contextText || ''}`,
    };
  })();

  const [open, setOpen] = useState(false);
  const [maximized, setMaximized] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [sessions, setSessions] = useState<AssistantSession[]>([]);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamContent, setStreamContent] = useState('');
  const [streamReasoning, setStreamReasoning] = useState('');
  const [streamToolProgress, setStreamToolProgress] = useState<ChatToolProgress | null>(null);
  const [toolTrail, setToolTrail] = useState<ChatToolsEvent[]>([]);
  // "检索数据库"（Agent 工具）开关：默认跟随全局 agent_enabled，可逐会话切换
  const [agentOn, setAgentOn] = useState(false);
  // 首页/趋势页注入的论文库热门趋势（agent 关闭时也能用真实数据回答"热门趋势"）
  const [pageTrending, setPageTrending] = useState<string | null>(null);
  // 打开后待自动发送的问题（如 AI 分析按钮触发）
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);

  // —— 增强：模型选择 / 用量 / 窗口状态 / 首屏引导 ——
  const [models, setModels] = useState<Array<{ id: string; label: string }>>([]);
  const [chatModel, setChatModel] = useState('');
  const [showModelSelect, setShowModelSelect] = useState(false);
  const [lastUsage, setLastUsage] = useState<{ prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | null>(null);
  const [btnOffset, setBtnOffset] = useState({ x: 0, y: 0 }); // 悬浮按钮拖拽偏移
  const [showTour, setShowTour] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const historyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const nearBottomRef = useRef(true);       // 滚动防打断：仅在接近底部时自动下滚
  const dragRef = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null);
  const dragMovedRef = useRef(false);       // 拖拽发生位移时抑制按钮点击
  const btnOffsetRef = useRef(btnOffset);   // 拖拽最新位移（供 pointerup 保存，避免 state 未提交）
  const sendRef = useRef<typeof send>(async () => {});
  const closeRef = useRef<() => void>(() => {});
  // 语音输入（Web Speech API，Chrome/Edge 支持）
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<{ stop: () => void } | null>(null);

  const pageLabel = TAB_LABELS[`${ctx.page}:${ctx.tab}`] || PAGE_LABELS[ctx.page] || 'AI 助手';

  // —— 页面快捷操作（收藏/已读）依赖 ——
  const { toast } = useToast();
  const { has: hasBookmark, toggle: toggleBookmark } = useBookmarks();

  const handleToggleFavorite = async () => {
    if (!ctx.paperId) return;
    const nowBookmarked = await toggleBookmark(ctx.paperId);
    toast(nowBookmarked ? '已收藏该论文' : '已取消收藏', nowBookmarked ? 'success' : 'info');
  };

  const handleMarkRead = async () => {
    if (!ctx.paperId) return;
    await personalApi.recordReading(ctx.paperId).catch(() => {});
    toast('已标记为已读', 'success');
  };

  /** 语音输入：Web Speech API（Chrome/Edge），结果追加到输入框。 */
  const toggleVoice = () => {
    const SR = (window as unknown as { SpeechRecognition?: new () => { start: () => void; stop: () => void; lang: string; interimResults: boolean; onresult: (e: unknown) => void; onend: () => void; onerror: () => void }; webkitSpeechRecognition?: new () => { start: () => void; stop: () => void; lang: string; interimResults: boolean; onresult: (e: unknown) => void; onend: () => void; onerror: () => void } })
      .SpeechRecognition || (window as unknown as { webkitSpeechRecognition?: new () => { start: () => void; stop: () => void; lang: string; interimResults: boolean; onresult: (e: unknown) => void; onend: () => void; onerror: () => void } }).webkitSpeechRecognition;
    if (!SR) {
      toast('当前浏览器不支持语音输入（Chrome/Edge 可用）', 'warning');
      return;
    }
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }
    const rec = new SR();
    rec.lang = 'zh-CN';
    rec.interimResults = false;
    rec.onresult = (e: unknown) => {
      const ev = e as { results: ArrayLike<ArrayLike<{ transcript: string }>> };
      const text = Array.from(ev.results).map((r) => r[0].transcript).join('');
      if (text) setInput((v) => (v ? `${v}${text}` : text));
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recognitionRef.current = rec;
    try {
      rec.start();
      setListening(true);
    } catch { /* 未授权/不支持时静默 */ }
  };

  // 页面上下文变化 → 新会话
  useEffect(() => {
    setSessionId(null);
    setMessages([]);
    setStreamContent('');
    setStreamReasoning('');
    setStreamToolProgress(null);
    setToolTrail([]);
    setHistoryOpen(false);
    abortRef.current?.abort();
  }, [ctx.key]);

  // 读取全局 agent 开关（系统设置页持久化），作为本会话默认值；用户手动切换过则优先用本地记忆
  useEffect(() => {
    let cancelled = false;
    try {
      const v = localStorage.getItem('assistant_agent_on');
      if (v !== null) {
        setAgentOn(v === '1');
        return;
      }
    } catch { /* 忽略 */ }
    papersApi.getSettings()
      .then((s) => {
        if (cancelled) return;
        setAgentOn(!!s.agent_enabled);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // 模型列表（供头部模型选择器）；记忆上次选择
  useEffect(() => {
    let cancelled = false;
    papersApi.getAIAnalysisModels()
      .then((res) => {
        if (cancelled) return;
        const list = (res.models || [])
          .filter((m) => m.available)
          .map((m) => ({
            id: m.name,
            label: `${m.provider ? `${m.provider} ` : ''}${m.name.split('/').pop() || m.name}`,
          }));
        setModels(list);
        const last = getLastModel('assistant_chat');
        if (last && list.some((m) => m.id === last)) setChatModel(last);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // 窗口状态记忆：最大化 + 悬浮按钮拖拽偏移
  useEffect(() => {
    try {
      if (localStorage.getItem('assistant_maximized') === '1') setMaximized(true);
      const off = localStorage.getItem('assistant_btn_offset');
      if (off) {
        const p = JSON.parse(off) as { x: number; y: number };
        if (typeof p.x === 'number' && typeof p.y === 'number') {
          setBtnOffset(p);
          btnOffsetRef.current = p;
        }
      }
    } catch { /* 忽略 */ }
  }, []);

  // 首屏引导：第一次使用展示一条提示气泡
  useEffect(() => {
    try {
      if (localStorage.getItem('assistant_tour_done') !== '1') setShowTour(true);
    } catch { /* 忽略 */ }
  }, []);

  // 首页/趋势页：拉取论文库真实热门趋势注入会话上下文，agent 关闭时也能数据化回答
  useEffect(() => {
    let cancelled = false;
    if (ctx.page !== 'home' && ctx.page !== 'trends') {
      setPageTrending(null);
      return;
    }
    papersApi.getTrendingTopics()
      .then((res) => {
        if (cancelled) return;
        const list = (res.topics || []).slice(0, 8);
        if (list.length === 0) {
          setPageTrending(null);
          return;
        }
        const lines = list.map((t) =>
          `- ${t.topic}：当年 ${t.paper_count} 篇，同比 ${t.growth_rate > 0 ? `上升 ${(t.growth_rate * 100).toFixed(0)}%` : '平稳'}`
        ).join('\n');
        setPageTrending(`当前论文库热门趋势 Top${list.length}：\n${lines}\n\n（以上为论文库真实统计，回答热点问题时请优先引用）`);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [ctx.key, ctx.page]);

  // 监听外部「打开悬浮助手」事件（论文卡片 AI 分析按钮等）
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (((e as CustomEvent).detail || {})) as { paperId?: string; contextText?: string; autoPrompt?: string };
      setOverride({ paperId: detail.paperId, contextText: detail.contextText });
      setOpen(true);
      setPendingPrompt(detail.autoPrompt || null);
    };
    window.addEventListener('pp:open-assistant', handler);
    return () => window.removeEventListener('pp:open-assistant', handler);
  }, []);

  // 打开后自动发送预设问题（AI 分析按钮）：窗口出现即开始分析，内容直接流入窗口
  useEffect(() => {
    if (open && pendingPrompt && !streaming) {
      const prompt = pendingPrompt;
      setPendingPrompt(null);
      send(prompt);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pendingPrompt, streaming]);

  // 打开窗口时加载历史会话列表
  useEffect(() => {
    if (!open) return;
    assistantApi.listSessions(30).then(setSessions).catch(() => {});
  }, [open, ctx.key]);

  // 自动滚动到底部（防打断：用户上翻阅读时不强拉回底部）
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    if (nearBottomRef.current) {
      const el = scrollRef.current;
      if (el) el.scrollTo({ top: el.scrollHeight });
    }
  }, [messages, streamContent, streaming]);

  // 快捷键：Ctrl/Cmd+K 唤起/收起，Esc 关闭，Ctrl+Enter 发送
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
        return;
      }
      if (e.key === 'Escape' && open) {
        closeRef.current();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !streaming && input.trim()) {
        e.preventDefault();
        sendRef.current();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, streaming, input]);

  // 打开窗口时自动聚焦输入框
  useEffect(() => {
    if (open) {
      const t = setTimeout(() => inputRef.current?.focus(), 60);
      return () => clearTimeout(t);
    }
  }, [open]);

  // 输入框自适应高度（单行到最多 120px）
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [input]);

  // 最大化时锁定页面滚动，避免滚轮滚到背后的内容
  useEffect(() => {
    if (!open || !maximized) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [open, maximized]);

  const loadSessions = useCallback(() => {
    assistantApi.listSessions(30).then(setSessions).catch(() => {});
  }, []);

  const send = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || streaming) return;
    const userMsg: ChatMessageItem = { role: 'user', content: text, ts: Date.now() };
    setMessages((m) => [...m, userMsg]);
    setInput('');
    setStreaming(true);
    setStreamContent('');
    setStreamReasoning('');
    setStreamToolProgress(null);
    setToolTrail([]);
    setLastUsage(null);
    setHistoryOpen(false);

    let sid = sessionId;
    try {
      if (sid === null) {
        const contextPieces = [ctx.contextText, pageTrending].filter(Boolean).join('\n\n');
        const created = await assistantApi.createSession(ctx.page, {
          ...(ctx.paperId ? { paper_id: ctx.paperId } : {}),
          ...(contextPieces ? { context_text: contextPieces } : {}),
        });
        sid = created.id;
        setSessionId(sid);
      }
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: `[Error] 创建会话失败：${e instanceof Error ? e.message : '未知错误'}`, ts: Date.now() }]);
      setStreaming(false);
      return;
    }

    const activeSessionId = sid as number;
    const controller = new AbortController();
    abortRef.current = controller;
    let fullContent = '';
    let fullReasoning = '';

    /** 发起一轮流式；网络断流（非用户停止）时自动重连一次。 */
    const runStream = async (attempt: number): Promise<void> => {
      fullContent = '';
      fullReasoning = '';
      try {
        await streamAssistantDirect(activeSessionId, [{ role: 'user', content: userMsg.content }], (ev) => {
          if (ev.error) {
            setMessages((m) => [...m, { role: 'assistant', content: `[Error] ${ev.error}`, ts: Date.now() }]);
            setStreamContent('');
            setStreamReasoning('');
            setStreamToolProgress(null);
          } else if (ev.done) {
            if (fullContent) {
              const assistantMsg: ChatMessageItem = { role: 'assistant', content: fullContent, reasoning: fullReasoning || undefined, ts: Date.now() };
              setMessages((m) => [...m, assistantMsg]);
              assistantApi.saveMessages(activeSessionId, [
                { role: 'user', content: userMsg.content },
                { role: 'assistant', content: fullContent, reasoning: fullReasoning || undefined },
              ]).catch(() => {});
              loadSessions();
            }
            setStreamContent('');
            setStreamReasoning('');
            setStreamToolProgress(null);
          } else if (ev.content) {
            fullContent += ev.content;
            setStreamContent(fullContent);
          } else if (ev.reasoning) {
            fullReasoning += ev.reasoning;
            setStreamReasoning(fullReasoning);
          } else if (ev.tool_progress) {
            setStreamToolProgress(ev.tool_progress);
          } else if (ev.tools) {
            // 工具轨迹里的论文并入当前流（引用 [n] 可点击）；结束后保留为「AI 工作流」
            setToolTrail(ev.tools as ChatToolsEvent[]);
          } else if (ev.usage) {
            setLastUsage(ev.usage);
          }
        }, controller.signal, agentOn, chatModel || undefined);

        // 手动停止：保留已生成内容（不落库），而不是丢弃
        if (controller.signal.aborted && fullContent) {
          setMessages((m) => [...m, {
            role: 'assistant',
            content: `${fullContent}\n\n> ⏹ 已停止生成`,
            reasoning: fullReasoning || undefined,
            ts: Date.now(),
          }]);
          setStreamContent('');
          setStreamReasoning('');
          setStreamToolProgress(null);
        }
      } catch (e) {
        const isAbort = !!(e && (e as Error).name === 'AbortError');
        if (!isAbort && attempt < 2) {
          // 断流：清掉半成品，短暂等待后重连一次
          setStreamContent('');
          setStreamReasoning('');
          setStreamToolProgress(null);
          await new Promise((r) => setTimeout(r, 800));
          await runStream(attempt + 1);
          return;
        }
        throw e;
      }
    };

    try {
      await runStream(1);
    } catch (e) {
      if (e && (e as Error).name !== 'AbortError') {
        setMessages((m) => [...m, { role: 'assistant', content: `[Error] ${(e as Error).message}`, ts: Date.now() }]);
      }
      setStreamContent('');
      setStreamReasoning('');
      setStreamToolProgress(null);
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setStreaming(false);
    }
  };

  const openHistoryItem = async (id: number) => {
    try {
      const detail = await assistantApi.getSession(id);
      setSessionId(id);
      setMessages(detail.messages.map((m) => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
        reasoning: m.reasoning || undefined,
        ts: Date.now(),
      })));
      setStreamContent('');
      setStreamReasoning('');
      setStreamToolProgress(null);
      setToolTrail([]);
      setHistoryOpen(false);
    } catch { /* ignore */ }
  };

  const deleteHistoryItem = async (id: number) => {
    try {
      await assistantApi.deleteSession(id);
      if (sessionId === id) {
        setSessionId(null);
        setMessages([]);
      }
      loadSessions();
    } catch { /* ignore */ }
  };

  const newChat = () => {
    setSessionId(null);
    setMessages([]);
    setStreamContent('');
    setStreamReasoning('');
    setStreamToolProgress(null);
    setToolTrail([]);
    setHistoryOpen(false);
    abortRef.current?.abort();
  };

  const closeWindow = () => {
    abortRef.current?.abort();
    setOpen(false);
    setHistoryOpen(false);
  };

  // 供快捷键使用的最新引用（send/closeWindow 随每次渲染刷新）
  sendRef.current = send;
  closeRef.current = closeWindow;

  const toggleAgent = () => {
    setAgentOn((v) => {
      const nv = !v;
      try { localStorage.setItem('assistant_agent_on', nv ? '1' : '0'); } catch {}
      return nv;
    });
  };

  const toggleMax = () => {
    setMaximized((v) => {
      const nv = !v;
      try { localStorage.setItem('assistant_maximized', nv ? '1' : '0'); } catch {}
      return nv;
    });
  };

  const handleExport = () => {
    if (messages.length === 0) return;
    // 收集工具轨迹里检索到的论文，去重后作为引用附录
    const refs: Array<{ n?: number; title: string; url?: string; source?: string }> = [];
    for (const t of toolTrail) {
      for (const p of t.papers || []) {
        if (p.id && !refs.some((r) => r.title === p.title)) {
          refs.push({ n: p.n, title: p.title, url: p.url, source: p.source });
        }
      }
    }
    const extra = refs.length > 0
      ? `\n\n## 📚 引用论文\n\n${refs.map((r) => `[${r.n ?? ''}] ${r.title}${r.url ? `\n${r.url}` : ''}`).join('\n\n')}`
      : undefined;
    downloadChatMarkdown(pageLabel || 'AI 助手', `AI助手对话_${new Date().toISOString().slice(0, 10)}.md`, messages, extra);
  };

  /** 错误气泡上的「重试」：找到该错误前最近的一条用户消息重新发送。 */
  const handleRetry = useCallback((errMsg: ChatMessageItem) => {
    const idx = messages.indexOf(errMsg);
    const lastUser = [...messages.slice(0, idx)].reverse().find((m) => m.role === 'user');
    if (lastUser) send(lastUser.content);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  // 👍/👎 反馈：落到后端 ai_feedback 表（surface=assistant_chat, ref_id=会话 id, content_hash 用于按答案去重）
  const handleFeedback = useCallback((msg: ChatMessageItem, rating: 1 | -1) => {
    assistantApi.submitFeedback({
      surface: 'assistant_chat',
      ref_id: sessionId != null ? String(sessionId) : undefined,
      content_hash: hashString(msg.content),
      rating,
    }).catch(() => {});
  }, [sessionId]);

  // 关闭/页面切换时中断未完成流
  useEffect(() => () => abortRef.current?.abort(), []);

  const suggestions = SUGGESTIONS[`${ctx.page}:${ctx.tab}`] || SUGGESTIONS[ctx.page] || SUGGESTIONS.generic;

  return (
    <>
      {/* 悬浮按钮（可拖拽；有会话时显示红点） */}
      {!open && (
        <div
          className="fixed bottom-6 right-6 z-50"
          style={{ transform: `translate(${btnOffset.x}px, ${btnOffset.y}px)` }}
        >
          {showTour && (
            <div className="absolute bottom-full right-0 mb-3 w-56 rounded-xl bg-white dark:bg-gray-800 shadow-xl border border-gray-200 dark:border-gray-700 p-3 text-sm text-gray-700 dark:text-gray-200">
              <p>👋 有任何问题随时问我——包括论文、趋势、选题等，我会结合当前页面回答。</p>
              <button
                onClick={() => { setShowTour(false); try { localStorage.setItem('assistant_tour_done', '1'); } catch {} }}
                className="mt-2 text-xs text-primary-600 hover:underline"
              >
                知道了
              </button>
            </div>
          )}
          <button
            onPointerDown={(e) => {
              if (e.button !== 0) return;
              dragRef.current = { sx: e.clientX, sy: e.clientY, ox: btnOffset.x, oy: btnOffset.y };
              dragMovedRef.current = false;
              (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
            }}
            onPointerMove={(e) => {
              const d = dragRef.current;
              if (!d) return;
              const nx = d.ox + (e.clientX - d.sx);
              const ny = d.oy + (e.clientY - d.sy);
              if (Math.abs(nx - d.ox) > 3 || Math.abs(ny - d.oy) > 3) dragMovedRef.current = true;
              btnOffsetRef.current = { x: nx, y: ny };
              setBtnOffset({ x: nx, y: ny });
            }}
            onPointerUp={() => {
              if (!dragRef.current) return;
              dragRef.current = null;
              try { localStorage.setItem('assistant_btn_offset', JSON.stringify(btnOffsetRef.current)); } catch {}
            }}
            onClick={() => {
              if (dragMovedRef.current) { dragMovedRef.current = false; return; }
              setOpen(true);
            }}
            className="relative w-14 h-14 rounded-full bg-gradient-to-br from-purple-600 to-indigo-600 text-white shadow-lg shadow-purple-500/30 flex items-center justify-center hover:scale-105 active:scale-95 transition-transform cursor-grab active:cursor-grabbing"
            title="AI 助手"
          >
            <Sparkles className="w-6 h-6" />
            {sessionId != null && (
              <span className="absolute top-0.5 right-0.5 w-3 h-3 rounded-full bg-red-500 border-2 border-white dark:border-gray-900" />
            )}
          </button>
        </div>
      )}

      {/* 对话窗 */}
      {open && (
        <div
          className={`fixed z-50 flex flex-col rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden transition-all ${
            maximized
              ? 'inset-4 sm:inset-6'
              : 'bottom-24 right-4 sm:right-6 w-[min(400px,92vw)] h-[min(620px,78vh)]'
          }`}
        >
          {/* 头部 */}
          <div className="flex items-center gap-2 px-3.5 py-2.5 bg-gradient-to-r from-purple-600 to-indigo-600 text-white shrink-0">
            <Sparkles className="w-4 h-4" />
            <span className="font-medium text-sm truncate">{pageLabel}</span>
            <span className="text-[10px] text-white/70 truncate">{sessionId ? `会话 #${sessionId}` : '新会话'}</span>
            <div className="ml-auto flex items-center gap-0.5 shrink-0">
              {/* 模型选择 */}
              {models.length > 0 && (
                <div className="relative">
                  <button
                    onClick={() => setShowModelSelect((v) => !v)}
                    className="flex items-center gap-1 px-1.5 py-1 rounded-md text-[10px] text-white/80 hover:bg-white/15 transition-colors"
                    title="选择模型"
                  >
                    <Brain className="w-3 h-3" />
                    <span className="max-w-[90px] truncate">{models.find((m) => m.id === chatModel)?.label || '默认'}</span>
                    <ChevronDown className="w-2.5 h-2.5" />
                  </button>
                  {showModelSelect && (
                    <div className="absolute right-0 top-8 z-30 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg py-1 min-w-[170px] max-h-64 overflow-y-auto">
                      <button
                        onClick={() => { setChatModel(''); rememberModel('assistant_chat', null); setShowModelSelect(false); }}
                        className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${chatModel === '' ? 'text-purple-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                      >
                        默认模型
                      </button>
                      {models.map((m) => (
                        <button
                          key={m.id}
                          onClick={() => { setChatModel(m.id); rememberModel('assistant_chat', m.id); setShowModelSelect(false); }}
                          className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${chatModel === m.id ? 'text-purple-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                        >
                          {m.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              <button
                onClick={toggleAgent}
                className={`flex items-center gap-1 px-1.5 py-1 rounded-md text-[10px] transition-colors ${
                  agentOn ? 'bg-white/25 text-white' : 'text-white/70 hover:bg-white/15'
                }`}
                title={agentOn ? '已开启数据库检索（Agent 工具）' : '开启数据库检索（Agent 工具）'}
              >
                <Search className="w-3 h-3" />
                <span>{agentOn ? '检索开' : '检索'}</span>
              </button>
              <button onClick={() => { setHistoryOpen(!historyOpen); }} className="p-1.5 rounded-md hover:bg-white/15 transition-colors" title="历史会话">
                <History className="w-4 h-4" />
              </button>
              <button
                onClick={handleExport}
                disabled={messages.length === 0}
                className="p-1.5 rounded-md hover:bg-white/15 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                title="导出对话为 Markdown"
              >
                <Download className="w-4 h-4" />
              </button>
              <button onClick={toggleMax} className="p-1.5 rounded-md hover:bg-white/15 transition-colors" title={maximized ? '还原' : '放大'}>
                {maximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
              </button>
              <button onClick={closeWindow} className="p-1.5 rounded-md hover:bg-white/15 transition-colors" title="关闭">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* 主体：历史面板 或 消息区 */}
          <div className="flex-1 min-h-0 relative">
            {historyOpen ? (
              <div ref={historyRef} className="absolute inset-0 overflow-y-auto p-3 space-y-1.5">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-medium text-gray-500">历史会话</h4>
                  <button onClick={newChat} className="flex items-center gap-1 text-xs text-primary-600 hover:underline">
                    <Plus className="w-3 h-3" /> 新会话
                  </button>
                </div>
                {sessions.length === 0 && <p className="text-xs text-gray-400 text-center py-6">暂无历史会话</p>}
                {sessions.map((s) => (
                  <div
                    key={s.id}
                    className={`flex items-center gap-2 px-2.5 py-2 rounded-lg border text-xs cursor-pointer transition-colors ${
                      sessionId === s.id
                        ? 'border-purple-300 bg-purple-50 dark:bg-purple-900/20'
                        : 'border-gray-100 dark:border-gray-700 hover:border-purple-200'
                    }`}
                    onClick={() => openHistoryItem(s.id)}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="truncate text-gray-800 dark:text-gray-200">{s.title || '（无标题）'}</div>
                      <div className="text-[10px] text-gray-400">
                        {PAGE_LABELS[s.page] || s.page} · {s.message_count} 条
                        {s.updated_at ? ` · ${new Date(s.updated_at).toLocaleDateString()}` : ''}
                      </div>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteHistoryItem(s.id); }}
                      className="p-1 rounded text-gray-400 hover:text-red-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                      title="删除"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div ref={scrollRef} className="h-full overflow-y-auto px-3.5 py-3">
                {messages.length === 0 && !streaming ? (
                  <div className="h-full flex flex-col items-center justify-center gap-4">
                    <div className="text-center">
                      <Sparkles className="w-8 h-8 text-purple-400 mx-auto mb-2" />
                      <p className="text-sm text-gray-500">在「{pageLabel}」页面向我提问</p>
                      <p className="text-xs text-gray-400 mt-1">我会结合当前页面内容回答</p>
                    </div>
                    <div className="flex flex-wrap justify-center gap-2 px-2">
                      {suggestions.map((s) => (
                        <button
                          key={s}
                          onClick={() => { send(s); }}
                          className="px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-600 text-xs text-gray-600 dark:text-gray-300 hover:border-purple-400 hover:text-purple-600 dark:hover:text-purple-300 transition-colors"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <ChatMessageList
                    messages={messages}
                    streaming={streaming ? { content: streamContent, reasoning: streamReasoning, toolProgress: streamToolProgress } : null}
                    tools={toolTrail}
                    citations={{}}
                    accent="bg-purple-600"
                    emptyText=""
                    onFeedback={handleFeedback}
                    onRetry={handleRetry}
                  />
                )}

                {/* 用量提示（best-effort，提供方返回才显示） */}
                {lastUsage && !streaming && lastUsage.total_tokens != null && (
                  <div className="mt-2 text-center text-[10px] text-gray-400">
                    ⚡ 本回答用量：输入 {lastUsage.prompt_tokens ?? '-'} · 输出 {lastUsage.completion_tokens ?? '-'} tokens
                  </div>
                )}

                {/* 页面快捷操作：论文上下文时提供收藏/已读 */}
                {ctx.paperId && messages.length > 0 && !streaming && (
                  <div className="mt-2 flex justify-center gap-2 border-t border-gray-100 dark:border-gray-700 pt-2">
                    <button
                      onClick={handleToggleFavorite}
                      className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md text-gray-500 dark:text-gray-400 hover:text-yellow-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                    >
                      <Bookmark className={`w-3 h-3 ${hasBookmark(ctx.paperId) ? 'fill-yellow-500 text-yellow-500' : ''}`} />
                      {hasBookmark(ctx.paperId) ? '已收藏' : '收藏论文'}
                    </button>
                    <button
                      onClick={handleMarkRead}
                      className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md text-gray-500 dark:text-gray-400 hover:text-green-600 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                    >
                      ✔ 标记已读
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 底部输入 */}
          <div className="shrink-0 border-t border-gray-100 dark:border-gray-700 p-2 sm:p-2.5 flex items-center gap-1.5 sm:gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={1}
              placeholder="输入问题，Enter 发送，Shift+Enter 换行"
              className="flex-1 px-2.5 sm:px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-purple-500 resize-none overflow-y-auto"
              style={{ maxHeight: 120 }}
            />
            <button
              onClick={toggleVoice}
              className={`w-9 h-9 shrink-0 rounded-lg flex items-center justify-center transition-colors ${
                listening
                  ? 'bg-red-500 text-white animate-pulse'
                  : 'text-gray-400 hover:text-purple-600 hover:bg-gray-100 dark:hover:bg-gray-700'
              }`}
              title={listening ? '停止录音' : '语音输入'}
            >
              {listening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            </button>
            {streaming ? (
              <button
                onClick={() => abortRef.current?.abort()}
                className="w-9 h-9 shrink-0 rounded-lg bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 flex items-center justify-center hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                title="停止生成"
              >
                <Square className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={() => send()}
                disabled={!input.trim()}
                className="w-9 h-9 shrink-0 rounded-lg bg-purple-600 text-white flex items-center justify-center disabled:opacity-50 hover:bg-purple-700 transition-colors"
                title="发送"
              >
                <Send className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      )}
    </>
  );
}
