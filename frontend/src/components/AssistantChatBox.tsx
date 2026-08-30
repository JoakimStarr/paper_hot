'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, Square, Loader2, ChevronDown } from 'lucide-react';
import ChatMessageList, { ChatMessageItem, ChatToolsEvent, ChatToolProgress } from '@/components/ChatMessageList';
import { assistantApi, papersApi, getLastModel, rememberModel } from '@/lib/api';
import { streamAssistantDirect } from '@/lib/assistantStream';

/**
 * 内嵌 AI 对话框：复用悬浮助手的直连后端 SSE 流式 + ChatMessageList 渲染，
 * 直接展示在页面卡片内（不弹悬浮窗）。
 *
 * - 直连后端（绕过 Next dev 代理缓冲）→ 真正的逐字流式；
 * - 预置 autoPrompt：点「开始」即发起一次预置指令（如辩论/答辩）；
 * - 之后可在输入框继续追问。
 */
export default function AssistantChatBox({ title, subtitle, page, contextText, autoPrompt, startLabel, icon, accentBtn }: {
  title: string;
  subtitle?: string;
  page: string;
  contextText: string;
  autoPrompt?: string;
  startLabel?: string;
  icon?: React.ReactNode;
  accentBtn?: string;   // 开始/发送按钮主色 class，默认 primary
}) {
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamContent, setStreamContent] = useState('');
  const [streamReasoning, setStreamReasoning] = useState('');
  const [streamToolProgress, setStreamToolProgress] = useState<ChatToolProgress | null>(null);
  const [toolTrail, setToolTrail] = useState<ChatToolsEvent[]>([]);
  const [agentOn, setAgentOn] = useState(true); // 工具检索默认开：辩论/答辩需查库证据
  const [chatModel, setChatModel] = useState('');
  const [models, setModels] = useState<Array<{ id: string; label: string }>>([]);
  const [showModelSelect, setShowModelSelect] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 模型列表 + 记忆（与悬浮助手共用 assistant_chat 记忆，保持一致）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await papersApi.getAIAnalysisModels();
        const bare = (n: string) => (n.includes('/') ? n.split('/').slice(1).join('/') : n);
        const list = (res.models || [])
          .filter((m) => m.available)
          .map((m) => ({ id: m.name, label: `${m.provider ? `${m.provider} · ` : ''}${bare(m.name)}` }));
        if (cancelled) return;
        setModels(list);
        const last = getLastModel('assistant_chat');
        if (last && list.some((m) => m.id === last)) setChatModel(last);
      } catch { /* 模型列表加载失败：仍可用默认模型 */ }
    })();
    return () => { cancelled = true; };
  }, []);

  // 自动滚动到底部（新消息 / 流式增量）
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streamContent, streamReasoning]);

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

    let sid = sessionId;
    try {
      if (sid === null) {
        const created = await assistantApi.createSession(page, contextText ? { context_text: contextText } : undefined);
        sid = created.id;
        setSessionId(sid);
      }
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: `[Error] 创建会话失败：${e instanceof Error ? e.message : '未知错误'}`, ts: Date.now() }]);
      setStreaming(false);
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    let fullContent = '';
    let fullReasoning = '';
    try {
      await streamAssistantDirect(sid as number, [{ role: 'user', content: text }], (ev) => {
        if (ev.error) {
          setMessages((m) => [...m, { role: 'assistant', content: `[Error] ${ev.error}`, ts: Date.now() }]);
          setStreamContent('');
          setStreamReasoning('');
          setStreamToolProgress(null);
        } else if (ev.done) {
          if (fullContent) {
            const assistantMsg: ChatMessageItem = { role: 'assistant', content: fullContent, reasoning: fullReasoning || undefined, ts: Date.now() };
            setMessages((m) => [...m, assistantMsg]);
            assistantApi.saveMessages(sid as number, [
              { role: 'user', content: text },
              { role: 'assistant', content: fullContent, reasoning: fullReasoning || undefined },
            ]).catch(() => {});
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
          setStreamToolProgress(ev.tool_progress as ChatToolProgress);
        } else if (ev.tools) {
          setToolTrail(ev.tools as ChatToolsEvent[]);
        }
      }, controller.signal, agentOn, chatModel || undefined);
    } catch (e: unknown) {
      if ((e as Error).name !== 'AbortError') {
        setMessages((m) => [...m, { role: 'assistant', content: `[Error] ${(e as Error).message}`, ts: Date.now() }]);
      }
    } finally {
      setStreaming(false);
    }
  };

  const stop = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const btnCls = accentBtn || 'bg-primary-600 hover:bg-primary-700';

  return (
    <div className="flex flex-col h-[460px]">
      {/* 头部：标题 + 模型选择 + 工具开关 */}
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          {icon}
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate">{title}</h3>
          {subtitle && <span className="text-[11px] font-normal text-gray-400 hidden sm:inline">{subtitle}</span>}
        </div>
        <div className="flex items-center gap-2">
          <label className="inline-flex items-center gap-1 text-[11px] text-gray-500 dark:text-gray-400 cursor-pointer select-none" title="允许 AI 调用论文库工具检索证据">
            <input type="checkbox" checked={agentOn} onChange={(e) => setAgentOn(e.target.checked)} className="w-3 h-3 accent-purple-600" />
            工具检索
          </label>
          <div className="relative">
            <button
              onClick={() => setShowModelSelect((v) => !v)}
              className="inline-flex items-center gap-1 px-2 py-1 text-[11px] text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              {chatModel ? (models.find((m) => m.id === chatModel)?.label || chatModel) : '默认模型'}
              <ChevronDown className={`w-3 h-3 transition-transform ${showModelSelect ? 'rotate-180' : ''}`} />
            </button>
            {showModelSelect && (
              <div className="absolute right-0 top-8 z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg py-1 min-w-[200px] max-h-64 overflow-y-auto">
                <button
                  onClick={() => { rememberModel('assistant_chat', null); setChatModel(''); setShowModelSelect(false); }}
                  className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${chatModel === '' ? 'text-purple-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                >
                  默认（跟随全局设置）
                </button>
                {models.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => { rememberModel('assistant_chat', m.id); setChatModel(m.id); setShowModelSelect(false); }}
                    className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${chatModel === m.id ? 'text-purple-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 消息区 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto rounded-lg bg-gray-50 dark:bg-gray-900/40 border border-gray-200 dark:border-gray-700 p-3">
        <ChatMessageList
          messages={messages}
          streaming={streaming ? { content: streamContent, reasoning: streamReasoning, toolProgress: streamToolProgress } : null}
          tools={toolTrail}
          citations={{}}
          accent={accentBtn || 'bg-primary-600'}
          emptyText={autoPrompt ? `点击下方「${startLabel || '开始'}」发起` : '开始对话吧'}
        />
      </div>

      {/* 输入区 */}
      <div className="mt-2">
        {autoPrompt && messages.length === 0 && !streaming && (
          <button
            onClick={() => send(autoPrompt)}
            className={`w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 ${btnCls} text-white text-sm rounded-lg transition-colors`}
          >
            {startLabel || '开始'}
          </button>
        )}
        {messages.length > 0 && (
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
              rows={1}
              placeholder="追问交锋细节，Enter 发送，Shift+Enter 换行"
              className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-1 focus:ring-primary-400 resize-none max-h-24"
            />
            {streaming ? (
              <button onClick={stop} className="inline-flex items-center gap-1 px-3 py-2 bg-red-500 hover:bg-red-600 text-white text-sm rounded-lg transition-colors">
                <Square className="w-4 h-4" />
              </button>
            ) : (
              <button onClick={() => send()} disabled={!input.trim()} className={`inline-flex items-center gap-1 px-3 py-2 ${btnCls} disabled:opacity-40 text-white text-sm rounded-lg transition-colors`}>
                <Send className="w-4 h-4" />
              </button>
            )}
            {streaming && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
          </div>
        )}
      </div>
    </div>
  );
}
