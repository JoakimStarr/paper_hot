'use client';

import React from 'react';
import { Loader2 } from 'lucide-react';

export interface StatusMetric {
  label: string;
  value: React.ReactNode;
  /** good=绿 / bad=红 / accent=面板主题色加粗 / 缺省灰 */
  tone?: 'good' | 'bad' | 'accent';
}

interface TaskStatusPanelProps {
  /** 主题色：blue=关键词 / teal=参考文献 */
  tone: 'blue' | 'teal';
  running: boolean;
  runningText: string;
  idleText: string;
  statusLabel: string;
  /** 任务标题（关键词 / 论文标题），超长截断 */
  title?: string | null;
  /** 指标 chips */
  metrics?: StatusMetric[];
  /** 最近日志行 */
  log?: string[];
  logTitle: string;
  message?: string | null;
  /** 状态行右侧操作区（暂停/停止按钮等） */
  actions?: React.ReactNode;
  /** 自定义扩展区（如关键词任务进度条），渲染在指标行之前 */
  children?: React.ReactNode;
}

const TONE = {
  blue: {
    wrap: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800',
    accent: 'text-blue-600 dark:text-blue-400',
  },
  teal: {
    wrap: 'bg-teal-50 dark:bg-teal-900/20 border-teal-200 dark:border-teal-800',
    accent: 'text-teal-600 dark:text-teal-400',
  },
};

/** 爬虫任务状态块：状态行 + 指标 chips + 最近日志 + 结果消息（关键词/参考文献卡片共用） */
export default function TaskStatusPanel({
  tone, running, runningText, idleText, statusLabel, title, metrics, log, logTitle, message, actions, children,
}: TaskStatusPanelProps) {
  const t = TONE[tone];
  return (
    <div className={`mt-1 p-3 rounded-lg border text-xs text-gray-700 dark:text-gray-200 space-y-1 ${t.wrap}`}>
      <div className="flex items-center gap-2">
        <span className="text-gray-500 dark:text-gray-400">{statusLabel}:</span>
        <span className={`inline-flex items-center gap-1 font-medium ${running ? t.accent : 'text-gray-600 dark:text-gray-300'}`}>
          {running && <Loader2 className="w-3 h-3 animate-spin" />}
          {running ? runningText : idleText}
        </span>
        {title && <span className="truncate font-medium text-gray-800 dark:text-gray-100">{title}</span>}
        {actions && <span className="flex items-center gap-1 ml-auto shrink-0">{actions}</span>}
      </div>
      {children}
      {metrics && metrics.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-500 dark:text-gray-400">
          {metrics.map((m) => (
            <span key={m.label} className={
              m.tone === 'good' ? 'font-medium text-green-600 dark:text-green-400'
                : m.tone === 'bad' ? 'text-red-500'
                  : m.tone === 'accent' ? `font-medium ${t.accent}`
                    : ''
            }>
              {m.label}: {m.value}
            </span>
          ))}
        </div>
      )}
      {log && log.length > 0 && (
        <div className="pt-1">
          <div className="text-[11px] text-gray-400 mb-1">{logTitle}</div>
          <div className="max-h-24 overflow-y-auto rounded-md bg-gray-50 dark:bg-gray-900/60 p-2 text-[10px] leading-4 text-gray-500 dark:text-gray-400 font-mono break-all">
            {log.slice(-6).map((l, i) => <div key={i}>{l}</div>)}
          </div>
        </div>
      )}
      {message && <div className="text-gray-600 dark:text-gray-300 break-words">{message}</div>}
    </div>
  );
}
