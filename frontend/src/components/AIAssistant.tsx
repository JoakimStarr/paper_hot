'use client';

/**
 * 全局 AI 悬浮助手：所有页面右下角悬浮按钮 → 点击弹开对话窗。
 * - 按当前页面注入上下文（论文详情 / 趋势 / 选题 / 检索 / 工作台 …），回答贴合页面。
 * - 会话管理：自动创建会话并保存历史记录，支持历史列表 / 加载 / 删除。
 * - 支持最大化（放大）。
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { usePathname } from 'next/navigation';
import { MessageCircle, X, Maximize2, Minimize2, Send, Loader2, Sparkles, History, Plus, Trash2, Search } from 'lucide-react';
import ChatMessageList, { ChatMessageItem, ChatToolsEvent, ChatToolProgress } from './ChatMessageList';
import { streamAssistantChat, assistantApi, papersApi, AssistantSession } from '@/lib/api';

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
  'topics:gaps': '研究空白助手',
  'topics:validator': '选题验证助手',
  'topics:library': '选题库助手',
  'topics:producer': '产出工作台助手',
};

// 子 tab 描述（注入上下文，帮助 AI 理解当前子页面）
const TAB_DESCRIPTIONS: Record<string, string> = {
  'dashboard:workbench': '正在研究工作台的「今日值得读」推荐列表',
  'dashboard:briefing': '正在查看工作台的「领域快讯」热点趋势',
  'dashboard:stack': '正在查看工作台的「我的研究栈」',
  'dashboard:prefs': '正在设置工作台的「推荐偏好」',
  'topics:gaps': '正在选题中心的「研究空白」页',
  'topics:validator': '正在选题中心的「选题验证」页',
  'topics:library': '正在选题中心的「选题库」页',
  'topics:producer': '正在选题中心的「产出工作台」页（综述生成/期刊适配）',
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
  'topics:gaps': ['当前有哪些研究空白？', '哪个空白最值得切入？', '帮我解释这个空白组合'],
  'topics:validator': ['帮我评估一个选题的可行性', '怎么判断选题的新颖性？', '我的选题有什么风险？'],
  'topics:library': ['我的选题库里哪个最值得推进？', '帮我比较两个选题'],
  'topics:producer': ['怎么生成一篇文献综述？', '我的选题适合投哪个期刊？'],
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
    tab = params.get('tab') || 'gaps';
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

  // 页面跳转时清除外部覆盖与 tab 上报
  useEffect(() => {
    setOverride(null);
    setPageTab(undefined);
  }, [derivedCtx.key]);

  // 监听页面内部子 tab 切换
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (((e as CustomEvent).detail || {})) as { tab?: string };
      setPageTab(detail.tab || undefined);
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
    const contextText = TAB_DESCRIPTIONS[`${derivedCtx.page}:${tab}`] || derivedCtx.contextText;
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
  // 流式调试计数：观察事件是否实时到达（临时，确认后移除）
  const [streamEvents, setStreamEvents] = useState(0);
  // "检索数据库"（Agent 工具）开关：默认跟随全局 agent_enabled，可逐会话切换
  const [agentOn, setAgentOn] = useState(false);
  // 首页/趋势页注入的论文库热门趋势（agent 关闭时也能用真实数据回答"热门趋势"）
  const [pageTrending, setPageTrending] = useState<string | null>(null);
  // 打开后待自动发送的问题（如 AI 分析按钮触发）
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const historyRef = useRef<HTMLDivElement>(null);

  const pageLabel = TAB_LABELS[`${ctx.page}:${ctx.tab}`] || PAGE_LABELS[ctx.page] || 'AI 助手';

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

  // 读取全局 agent 开关（系统设置页持久化），作为本会话默认值；应用加载时取一次即可
  useEffect(() => {
    let cancelled = false;
    papersApi.getSettings()
      .then((s) => {
        if (cancelled) return;
        setAgentOn(!!s.agent_enabled);
      })
      .catch(() => {});
    return () => { cancelled = true; };
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

  // 自动滚动到底部
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, streamContent, streaming]);

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
    setStreamEvents(0);
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
    try {
      await streamAssistantChat(activeSessionId, [{ role: 'user', content: userMsg.content }], {
        onContent: (t) => { setStreamContent(t); setStreamEvents((n) => n + 1); },
        onReasoning: (r) => { setStreamReasoning(r); setStreamEvents((n) => n + 1); },
        onToolProgress: (p) => { setStreamToolProgress(p); setStreamEvents((n) => n + 1); },
        onTools: (tools) => {
          // 工具轨迹里的论文并入当前流（引用 [n] 可点击）；结束后保留为「AI 工作流」
          setToolTrail(tools as ChatToolsEvent[]);
        },
        onDone: (full) => {
          if (full) {
            const assistantMsg: ChatMessageItem = { role: 'assistant', content: full, ts: Date.now() };
            setMessages((m) => [...m, assistantMsg]);
            assistantApi.saveMessages(activeSessionId, [
              { role: 'user', content: userMsg.content },
              { role: 'assistant', content: full },
            ]).catch(() => {});
            loadSessions();
          }
          setStreamContent('');
          setStreamReasoning('');
          setStreamToolProgress(null);
        },
        onError: (message) => {
          setMessages((m) => [...m, { role: 'assistant', content: `[Error] ${message}`, ts: Date.now() }]);
          setStreamContent('');
          setStreamReasoning('');
          setStreamToolProgress(null);
        },
      }, controller.signal, agentOn);
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
      setMessages(detail.messages.map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content, ts: Date.now() })));
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
      {/* 悬浮按钮 */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-br from-purple-600 to-indigo-600 text-white shadow-lg shadow-purple-500/30 flex items-center justify-center hover:scale-105 active:scale-95 transition-transform"
          title="AI 助手"
        >
          <Sparkles className="w-6 h-6" />
        </button>
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
            {streaming && (
              <span className="text-[10px] text-amber-200 shrink-0" title="流式调试：实时到达的事件数（确认流式后移除）">
                流式{streamEvents}条
              </span>
            )}
            <div className="ml-auto flex items-center gap-1 shrink-0">
              <button
                onClick={() => setAgentOn(!agentOn)}
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
              <button onClick={() => setMaximized(!maximized)} className="p-1.5 rounded-md hover:bg-white/15 transition-colors" title={maximized ? '还原' : '放大'}>
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
                  />
                )}
              </div>
            )}
          </div>

          {/* 底部输入 */}
          <div className="shrink-0 border-t border-gray-100 dark:border-gray-700 p-2.5 flex items-center gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) send(); }}
              placeholder="输入问题，Enter 发送"
              className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-purple-500"
            />
            <button
              onClick={() => send()}
              disabled={streaming || !input.trim()}
              className="w-9 h-9 shrink-0 rounded-lg bg-purple-600 text-white flex items-center justify-center disabled:opacity-50 hover:bg-purple-700 transition-colors"
              title="发送"
            >
              {streaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
