'use client';

/**
 * EntryCard —— 跨页入口卡（PAGE_REDESIGN §六）：引导用户跳转到关联分析页。
 */
import { ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronRight } from 'lucide-react';

interface Props {
  href: string;
  icon: ReactNode;
  title: string;
  desc?: string;
  className?: string;
}

export default function EntryCard({ href, icon, title, desc, className = '' }: Props) {
  const router = useRouter();

  return (
    <button
      onClick={() => router.push(href)}
      className={`w-full flex items-center gap-3 px-4 py-3 bg-gradient-to-r from-primary-50 to-blue-50 dark:from-primary-900/30 dark:to-blue-900/30 rounded-lg border border-primary-200 dark:border-primary-800 hover:border-primary-400 transition-colors text-left ${className}`}
    >
      <span className="text-primary-600 dark:text-primary-300 shrink-0">{icon}</span>
      <span className="flex-1 min-w-0">
        <span className="block text-sm font-medium text-gray-900 dark:text-white">{title}</span>
        {desc && <span className="block text-xs text-gray-500 dark:text-gray-400 truncate">{desc}</span>}
      </span>
      <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
    </button>
  );
}
