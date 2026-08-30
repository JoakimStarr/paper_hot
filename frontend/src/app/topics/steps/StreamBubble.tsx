'use client';

import React, { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { Loader2 } from 'lucide-react';

const MarkdownRenderer = dynamic(() => import('@/components/MarkdownRenderer'), {
  ssr: false,
  loading: () => <div className="h-16 flex items-center justify-center text-gray-400 text-sm animate-pulse">加载中...</div>,
});

export interface StreamBubbleData {
  id: string;
  label: string;
  text: string;
  reasoning: string;
  model?: string;
}

/**
 * 流式气泡（辩论/答辩共用），聊天窗口式：
 * - 头像（avatar）+ 角色侧标（sideLabel，如 正方/反方/评委）；
 *   avatarSide='right' 时头像在右侧（反方），否则在左侧；
 * - 流式进行中（streaming=true）用**纯文本**渲染正文——逐 token 零开销；
 * - 流式结束后（streaming=false）才切 MarkdownRenderer 渲染成文；
 * - React.memo：已完成轮次的 r 对象不再变化，增量更新只重渲染当前轮。
 */
function StreamBubbleImpl({ r, colorCls, streaming, citations, avatar, avatarSide = 'left', sideLabel }: {
  r: StreamBubbleData;
  colorCls: string;
  streaming: boolean;
  citations?: Record<number, { id: string; title?: string }>;
  avatar?: React.ReactNode;
  avatarSide?: 'left' | 'right';
  sideLabel?: string;
}) {
  // 思考计时：流式中且正文未产出时显示已等待秒数
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!streaming || r.text) return;
    const t0 = Date.now();
    setElapsed(0);
    const iv = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(iv);
  }, [streaming, r.text]);

  return (
    <div className={`flex items-end gap-2 ${avatarSide === 'right' ? 'flex-row-reverse' : ''}`}>
      {avatar && <div className="shrink-0">{avatar}</div>}
      <div className={`flex-1 min-w-0 rounded-lg border p-3 transition-all duration-300 ${colorCls}`}>
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          <span className="text-[11px] font-semibold text-gray-500 dark:text-gray-400">{sideLabel || r.label}</span>
          {r.model && (
            <span className="text-[10px] px-1.5 py-px rounded bg-white/70 dark:bg-gray-700/70 text-gray-400 font-mono">
              {r.model.split('/').pop()}
            </span>
          )}
          {streaming && !r.text && (
            <span className="inline-flex items-center gap-1 text-[11px] text-gray-400 animate-pulse">
              <Loader2 className="w-3 h-3 animate-spin" />
              {r.reasoning ? `思考中，即将成文… ${elapsed}s` : `思考中… ${elapsed}s`}
            </span>
          )}
        </div>

        {/* 思考过程：流式滚入（原生 details 折叠；流式中的当前轮默认展开） */}
        {r.reasoning && (
          <details className="mb-1.5" open={streaming}>
            <summary className="text-[10px] text-gray-400 cursor-pointer select-none hover:text-gray-500">思考过程</summary>
            <div className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap text-[11px] leading-relaxed text-gray-400/90 dark:text-gray-500">
              {r.reasoning}
            </div>
          </details>
        )}

        {/* 流式中：纯文本逐 token 更新；结束后：Markdown 成文 */}
        {streaming ? (
          <div className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700 dark:text-gray-300 min-h-[1em]">
            {r.text || (r.reasoning ? '' : '…')}
          </div>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <MarkdownRenderer content={r.text || ''} citations={citations} />
          </div>
        )}
      </div>
    </div>
  );
}

// 只比较内容字段（头像/侧标按角色固定，忽略），保证增量只重渲染当前轮
const StreamBubble = React.memo(StreamBubbleImpl, (prev, next) =>
  prev.r.text === next.r.text &&
  prev.r.reasoning === next.r.reasoning &&
  prev.r.model === next.r.model &&
  prev.r.label === next.r.label &&
  prev.streaming === next.streaming &&
  prev.colorCls === next.colorCls &&
  prev.citations === next.citations
);
export default StreamBubble;
