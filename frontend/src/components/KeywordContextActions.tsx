'use client';

/**
 * KeywordContextActions —— 关键词「上下文操作」可选集合（PAGE_REDESIGN §六）。
 * 全站复用：Atlas 节点详情、热点榜、空白卡片等挂同一组动作。
 * 查地图仅在 Atlas 内出现（传入 onMap 时渲染）。
 */
import { useRouter } from 'next/navigation';
import { Search, TrendingUp, Target, Map as MapIcon } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';

interface Props {
  keyword: string;
  /** Atlas 内使用：点击「查地图」回调（如滚动到研究版图） */
  onMap?: () => void;
  className?: string;
}

export default function KeywordContextActions({ keyword, onMap, className = '' }: Props) {
  const router = useRouter();
  const { t } = useLanguage();

  const toTopic = () => {
    try {
      localStorage.setItem('pp_topic_prefill', keyword);
    } catch { /* ignore */ }
    router.push('/topics?tab=validator');
  };

  const btn = 'flex items-center gap-1 px-2 py-1 text-xs rounded-md border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-primary-400 hover:text-primary-600 dark:hover:text-primary-300 transition-colors';

  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${className}`}>
      <button
        onClick={() => router.push(`/search?search=${encodeURIComponent(keyword)}&search_field=keyword`)}
        className={btn}
        title={t('net.ctxSearch')}
      >
        <Search className="w-3 h-3" />
        {t('net.ctxSearch')}
      </button>
      <button onClick={() => router.push('/trends')} className={btn} title={t('net.ctxTrend')}>
        <TrendingUp className="w-3 h-3" />
        {t('net.ctxTrend')}
      </button>
      <button onClick={toTopic} className={btn} title={t('net.ctxTopic')}>
        <Target className="w-3 h-3" />
        {t('net.ctxTopic')}
      </button>
      {onMap && (
        <button onClick={onMap} className={btn} title={t('net.ctxMap')}>
          <MapIcon className="w-3 h-3" />
          {t('net.ctxMap')}
        </button>
      )}
    </div>
  );
}
