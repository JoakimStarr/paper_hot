'use client';

/**
 * 共享聊天消息列表：用户/助手气泡 + 时间戳 + 一键复制为 Markdown + AI 工作流（工具调用/检索论文卡片）
 * + 引用编号 [n] → 论文详情页链接。趋势追问与论文详情的聊天窗口共用。
 */

import React, { useCallback, useMemo, useState } from 'react';
import MarkdownRenderer from './MarkdownRenderer';
import { Copy, Check, ChevronDown, ChevronRight, ExternalLink, Loader2, ThumbsUp, ThumbsDown } from 'lucide-react';

export interface ChatPaperRef {
  n?: number;
  id: string;
  title: string;
  url?: string;
  source?: string;
  published_at?: string;
  similarity?: number;
}

export interface ChatToolsEvent {
  tool: string;
  args?: Record<string, unknown>;
  papers?: ChatPaperRef[];
}

/** Agent 正在调用工具的实时提示（SSE tool_progress 载荷） */
export interface ChatToolProgress {
  tool: string;
  args?: Record<string, unknown>;
}

export interface ChatMessageItem {
  role: 'user' | 'assistant';
  content: string;
  ts?: number; // epoch ms
}

interface Props {
  messages: ChatMessageItem[];
  streaming?: { content: string; reasoning?: string; toolProgress?: ChatToolProgress | null } | null;
  /** 本次对话的工具调用轨迹（含检索到的论文），渲染成可展开的「AI 工作流」 */
  tools?: ChatToolsEvent[];
  /** 引用编号 → 论文：把 [n] 渲染成论文详情页链接 */
  citations?: Record<number, ChatPaperRef>;
  /** 用户气泡背景色（tailwind 类） */
  accent?: string;
  emptyText?: string;
  /** 反馈回调（👍/👎），由父级接入发送接口 */
  onFeedback?: (msg: ChatMessageItem, rating: 1 | -1) => void;
}

const TOOL_LABELS: Record<string, string> = {
  search_papers: '检索论文',
  retrieve_context: '语义召回相关论文',
  paper_trend: '查询发文趋势',
  keyword_gaps: '研究空白分析',
  subfield_distribution: '子领域分布',
  author_papers: '作者论文查询',
};

function formatTime(ts?: number): string {
  if (!ts) return '';
  const d = new Date(ts);
  const now = Date.now();
  const diff = now - ts;
  const pad = (n: number) => String(n).padStart(2, '0');
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (diff < 12 * 3600 * 1000 && d.getDate() === new Date(now).getDate()) return hm;
  return `${d.getMonth() + 1}-${d.getDate()} ${hm}`;
}

/** 把一段聊天导出为 .md 文件 */
export function downloadChatMarkdown(title: string, fileName: string, messages: ChatMessageItem[], extra?: string) {
  if (messages.length === 0) return;
  const lines = messages.map((msg) => {
    const role = msg.role === 'user' ? '👤 用户' : '🤖 AI';
    const ts = msg.ts ? `\n> 时间：${new Date(msg.ts).toLocaleString('zh-CN')}` : '';
    return `### ${role}${ts}\n\n${msg.content}\n`;
  });
  const content = `# ${title}\n\n> 导出时间：${new Date().toLocaleString('zh-CN')}${extra ? `\n${extra}` : ''}\n\n---\n\n${lines.join('\n---\n\n')}`;
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  a.click();
  URL.revokeObjectURL(url);
}

function WorkflowPanel({ tools }: { tools: ChatToolsEvent[] }) {
  const [open, setOpen] = useState(true);
  if (!tools || tools.length === 0) return null;
  return (
    <div className="mb-2 rounded-md border border-blue-100 dark:border-blue-800/60 bg-blue-50/60 dark:bg-blue-900/10">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-1.5 px-3 py-2 text-xs text-blue-600 dark:text-blue-300 font-medium hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        AI 工作流 · {tools.length} 步
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-2">
          {tools.map((t, i) => (
            <div key={i} className="text-xs">
              <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
                <span className="shrink-0 w-4 h-4 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-300 flex items-center justify-center text-[9px]">{i + 1}</span>
                <span className="font-medium">{TOOL_LABELS[t.tool] || t.tool}</span>
                {(() => {
                  const q = t.args?.query ? String(t.args.query) : (t.args?.keyword ? String(t.args.keyword) : '');
                  return q ? <span className="text-gray-400 truncate">“{q}”</span> : null;
                })()}
              </div>
              {t.papers && t.papers.length > 0 && (
                <div className="mt-1 pl-5.5 space-y-0.5">
                  {t.papers.slice(0, 6).map((p) => (
                    <a
                      key={`${p.id}-${p.n ?? 0}`}
                      href={p.url || `/paper/${p.id}`}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1.5 text-[11px] text-gray-600 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-300 group"
                    >
                      <ExternalLink className="w-2.5 h-2.5 text-gray-300 group-hover:text-blue-400 shrink-0" />
                      {p.n !== undefined && <span className="text-gray-400 shrink-0">[{p.n}]</span>}
                      <span className="truncate">{p.title}</span>
                      {p.source && <span className="text-gray-400 shrink-0">{p.source}</span>}
                    </a>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CopyButton({ text, className = '' }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* 剪贴板不可用时静默 */ }
  }, [text]);
  return (
    <button
      onClick={handleCopy}
      className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600/50 transition-colors ${className}`}
      title="一键复制为 Markdown"
    >
      {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
      {copied ? '已复制' : '复制'}
    </button>
  );
}

function FeedbackButtons({ msg, onFeedback }: { msg: ChatMessageItem; onFeedback?: (msg: ChatMessageItem, rating: 1 | -1) => void }) {
  const [sent, setSent] = useState<'up' | 'down' | null>(null);
  if (!onFeedback) return null;
  const handle = (rating: 1 | -1) => {
    if (sent) return;
    setSent(rating === 1 ? 'up' : 'down');
    onFeedback(msg, rating);
  };
  return (
    <span className="inline-flex items-center gap-0.5">
      <button
        onClick={() => handle(1)}
        className={`inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded transition-colors ${
          sent === 'up' ? 'text-green-600' : 'text-gray-400 hover:text-green-600 hover:bg-gray-100 dark:hover:bg-gray-600/50'
        }`}
        title="有帮助"
      >
        <ThumbsUp className="w-3 h-3" />
      </button>
      <button
        onClick={() => handle(-1)}
        className={`inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded transition-colors ${
          sent === 'down' ? 'text-red-500' : 'text-gray-400 hover:text-red-500 hover:bg-gray-100 dark:hover:bg-gray-600/50'
        }`}
        title="没帮助"
      >
        <ThumbsDown className="w-3 h-3" />
      </button>
    </span>
  );
}

export default function ChatMessageList({
  messages,
  streaming,
  tools,
  citations,
  accent = 'bg-purple-600',
  emptyText = '开始对话吧',
  onFeedback,
}: Props) {
  const citationsMap = useMemo(() => {
    const map: Record<number, ChatPaperRef> = {};
    if (citations) Object.assign(map, citations);
    // 工具轨迹里的论文也并入引用表（[n] → 链接）
    for (const t of tools || []) {
      for (const p of t.papers || []) {
        if (p.n !== undefined && !map[p.n]) map[p.n] = p;
      }
    }
    return map;
  }, [citations, tools]);

  if (messages.length === 0 && !streaming) {
    return <div className="text-center py-8 text-xs text-gray-400">{emptyText}</div>;
  }

  return (
    <div className="space-y-3">
      {tools && tools.length > 0 && <WorkflowPanel tools={tools} />}
      {messages.map((msg, i) => {
        const isUser = msg.role === 'user';
        return (
          <div key={i} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-lg px-3.5 py-2 text-sm ${
              isUser
                ? `${accent} text-white`
                : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
            }`}>
              {isUser ? (
                <div className="whitespace-pre-wrap break-words">{msg.content}</div>
              ) : (
                <MarkdownRenderer content={msg.content} citations={citationsMap} />
              )}
              <div className={`mt-1 flex items-center gap-1.5 ${isUser ? 'justify-end' : 'justify-start'}`}>
                {msg.ts && (
                  <span className={`text-[10px] ${isUser ? 'text-white/70' : 'text-gray-400'}`}>{formatTime(msg.ts)}</span>
                )}
                {!isUser && (
                  <>
                    <FeedbackButtons msg={msg} onFeedback={onFeedback} />
                    <CopyButton text={msg.content} />
                  </>
                )}
              </div>
            </div>
          </div>
        );
      })}

      {streaming && (
        <div className="flex justify-start">
          <div className="max-w-[85%] rounded-lg px-3.5 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200">
            {streaming.reasoning && !streaming.content && (
              <>
                <div className="text-xs text-blue-500 dark:text-blue-400 mb-1 font-medium">💭 思考中</div>
                <div className="text-xs text-blue-600 dark:text-blue-300 whitespace-pre-wrap">{streaming.reasoning}</div>
              </>
            )}
            {streaming.toolProgress && !streaming.content && (
              <div className="flex items-center gap-1.5 text-xs text-purple-600 dark:text-purple-300 mb-1">
                <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                <span>正在调用{TOOL_LABELS[streaming.toolProgress.tool] || streaming.toolProgress.tool}…</span>
                {(() => {
                  const a = streaming.toolProgress?.args;
                  const q = a ? String(a.query ?? a.keyword ?? '') : '';
                  return q ? <span className="text-gray-400 truncate max-w-[180px]">“{q}”</span> : null;
                })()}
              </div>
            )}
            {streaming.content && (
              <>
                {streaming.reasoning && (
                  <details className="mb-2">
                    <summary className="text-xs text-blue-500 dark:text-blue-400 cursor-pointer hover:text-blue-600">💭 查看思考</summary>
                    <div className="mt-1 p-2 bg-blue-50 dark:bg-blue-900/20 rounded text-xs text-blue-600 dark:text-blue-300 whitespace-pre-wrap">{streaming.reasoning}</div>
                  </details>
                )}
                <MarkdownRenderer content={streaming.content} citations={citationsMap} />
                <span className="inline-block w-1.5 h-4 bg-current ml-0.5 animate-pulse align-middle" />
              </>
            )}
            {!streaming.content && !streaming.reasoning && !streaming.toolProgress && (
              <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
