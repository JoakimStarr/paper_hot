'use client';

/**
 * SectionCard —— 统一的「标题 + 折叠 + 查看全部」区块壳（PAGE_REDESIGN §六）。
 */
import { useState, ReactNode } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

interface Props {
  title: ReactNode;
  children: ReactNode;
  /** 右上角动作区（如「查看全部」链接）；折叠按钮之外展示 */
  action?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}

export default function SectionCard({ title, children, action, defaultOpen = true, className = '' }: Props) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className={`bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 ${className}`}>
      <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-gray-100 dark:border-gray-700">
        <button
          onClick={() => setOpen(o => !o)}
          className="flex items-center gap-1 text-sm font-semibold text-gray-900 dark:text-white min-w-0"
        >
          {open ? <ChevronDown className="w-4 h-4 shrink-0 text-gray-400" /> : <ChevronRight className="w-4 h-4 shrink-0 text-gray-400" />}
          <span className="truncate">{title}</span>
        </button>
        {action && <div className="shrink-0 flex items-center gap-2">{action}</div>}
      </div>
      {open && <div className="p-4">{children}</div>}
    </section>
  );
}
