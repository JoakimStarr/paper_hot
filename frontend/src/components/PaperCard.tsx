'use client';

import React, { useState, memo } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { PaperCard as PaperCardType } from '@/types/paper';
import { ExternalLink, Calendar, TrendingUp, Bookmark, Sparkles, Pin, EyeOff } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { getIssuePeriod, topicColors } from '@/lib/utils';
import { useBookmarks } from '@/lib/useBookmarks';
import { usePins } from '@/lib/usePins';
import { usePreferences } from '@/lib/usePreferences';
import { useToast } from '@/components/Toast';
import { useAiAnalysisModal } from '@/components/AiAnalysisModalContext';

interface PaperCardProps {
  paper: PaperCardType;
  /** 多选模式（批量分析/批量导出），由列表页开启 */
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: (paperId: string) => void;
  /** 是否已读：true 时标题置灰并在标题处显示「已读」徽章 */
  read?: boolean;
}

// 卡片级「不感兴趣」快捷屏蔽的类型
type QuickHideOption = { type: 'subfield' | 'journal' | 'keyword' | 'author'; value: string; label: string };

const subfieldColors: Record<string, string> = {
  '宏观经济学': 'bg-blue-100 text-blue-800',
  '微观经济学': 'bg-green-100 text-green-800',
  '计量经济学': 'bg-purple-100 text-purple-800',
  '金融经济学': 'bg-yellow-100 text-yellow-800',
  '产业经济学': 'bg-red-100 text-red-800',
  '发展经济学': 'bg-indigo-100 text-indigo-800',
  '国际经济学': 'bg-pink-100 text-pink-800',
};

function PaperCardInner({ paper, selectable, selected, onToggleSelect, read }: PaperCardProps) {
  const { t } = useLanguage();
  const router = useRouter();
  const score = paper.final_score;
  const isTrending = paper.trend_score >= 0.6;
  const { has: isBookmarkedNow, toggle: toggleBookmarkState } = useBookmarks();
  const bookmarked = isBookmarkedNow(paper.id);
  const { has: isPinnedNow, toggle: togglePinState } = usePins();
  const pinned = isPinnedNow(paper.id);
  const { toast } = useToast();

  const handleToggleBookmark = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      const res = await toggleBookmarkState(paper.id);
      toast(t(res ? 'paper.bookmarkMsg' : 'paper.unbookmarkMsg'), 'success');
    } catch {
      toast(t('paper.bookmarkFailed'), 'error');
    }
  };

  const handleTogglePin = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      const res = await togglePinState(paper.id);
      if (res.limited) {
        toast(t('paper.pinLimit'), 'warning');
      } else {
        toast(t(res.pinned ? 'paper.pinnedMsg' : 'paper.unpinnedMsg'), 'success');
      }
    } catch {
      toast(t('paper.pinFailed'), 'error');
    }
  };

  // —— AI 分析：复用全局单例悬浮窗（P3），不再在卡片内维护弹窗状态，避免多卡片并发请求 ——
  const { openAiAnalysis } = useAiAnalysisModal();

  const handleOpenAi = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    openAiAnalysis(paper.id, paper.title);
  };

  // —— 「不感兴趣」快捷屏蔽：该论文的领域/期刊/关键词/作者入屏蔽表 ——
  const [hideOpen, setHideOpen] = useState(false);
  const { has: hasHidden, add: addPreference } = usePreferences();

  let quickHideOptions: QuickHideOption[] = [];
  if (paper.economics_subfield) {
    quickHideOptions.push({ type: 'subfield', value: paper.economics_subfield, label: `${t('pref.type.subfield')}：${paper.economics_subfield}` });
  }
  if (paper.journal_name) {
    quickHideOptions.push({ type: 'journal', value: paper.journal_name, label: `${t('pref.type.journal')}：${paper.journal_name}` });
  }
  (paper.keywords_cn || []).slice(0, 2).forEach((kw) => {
    if (kw) quickHideOptions.push({ type: 'keyword', value: kw, label: `${t('pref.type.keyword')}：${kw}` });
  });
  (paper.authors || []).slice(0, 2).forEach((au) => {
    if (au && au.trim()) quickHideOptions.push({ type: 'author', value: au.trim(), label: `${t('pref.type.author')}：${au.trim()}` });
  });
  // 过滤已在屏蔽表中的项，避免重复提示
  quickHideOptions = quickHideOptions.filter((o) => !hasHidden(o.type, o.value));

  const handleHide = async (option: QuickHideOption, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setHideOpen(false);
    try {
      await addPreference(option.type, option.value);
      toast(t('pref.hideMsg'), 'success');
    } catch {
      toast(t('pref.hideFailed'), 'error');
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md hover:shadow-lg transition-shadow duration-200 p-4 sm:p-6 border border-gray-200 dark:border-gray-700">
      <div className="flex justify-between items-start gap-2 mb-2 sm:mb-3">
        <div className="flex-1 min-w-0 flex items-start gap-2">
          {selectable && (
            <input
              type="checkbox"
              checked={!!selected}
              onChange={() => onToggleSelect?.(paper.id)}
              onClick={(e) => e.stopPropagation()}
              className="mt-1.5 w-4 h-4 accent-primary-600 cursor-pointer shrink-0"
              aria-label={t('paper.selectThis')}
            />
          )}
          <Link href={`/paper/${paper.id}`}>
            <div className="flex items-start gap-2 flex-1 min-w-0">
              <h3 className={`flex-1 min-w-0 text-base sm:text-lg font-semibold cursor-pointer line-clamp-2 ${
                read
                  ? 'text-gray-400 dark:text-gray-500 hover:text-gray-400 dark:hover:text-gray-500'
                  : 'text-gray-900 dark:text-white hover:text-primary-600 dark:hover:text-primary-400'
              }`}>
                {paper.title}
              </h3>
              {read && (
                <span className="shrink-0 inline-flex items-center px-1.5 py-0.5 mt-1 rounded text-[10px] font-medium bg-gray-200 dark:bg-gray-600 text-gray-500 dark:text-gray-300">
                  {t('paper.read')}
                </span>
              )}
            </div>
          </Link>
        </div>
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          {/* AI 分析快捷入口：打开全局单例悬浮窗展示 AI 分析报告 */}
          <button
            onClick={handleOpenAi}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded border bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-800 hover:bg-purple-100 dark:hover:bg-purple-900/50 transition-colors"
            title={t('paper.aiAnalyzeTitle')}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">{t('paper.aiAnalyze')}</span>
          </button>
          <button
            onClick={handleToggleBookmark}
            className="text-gray-400 dark:text-gray-500 hover:text-yellow-500 transition-colors p-1"
            title={bookmarked ? t('paper.unbookmark') : t('paper.bookmark')}
          >
            <Bookmark
              className={`w-4 h-4 sm:w-5 sm:h-5 ${bookmarked ? 'fill-yellow-500 text-yellow-500' : ''}`}
            />
          </button>
          <button
            onClick={handleTogglePin}
            className={`transition-colors p-1 ${pinned ? 'text-indigo-500 hover:text-indigo-600' : 'text-gray-400 dark:text-gray-500 hover:text-indigo-500'}`}
            title={pinned ? t('paper.unpin') : t('paper.pin')}
          >
            <Pin
              className={`w-4 h-4 sm:w-5 sm:h-5 ${pinned ? 'fill-indigo-500 text-indigo-500' : ''}`}
            />
          </button>
          {quickHideOptions.length > 0 && (
            <div className="relative">
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setHideOpen((v) => !v);
                }}
                className="transition-colors p-1 text-gray-400 dark:text-gray-500 hover:text-red-500"
                title={t('pref.title')}
              >
                <EyeOff className="w-4 h-4 sm:w-5 sm:h-5" />
              </button>
              {hideOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setHideOpen(false); }} />
                  <div className="absolute right-0 z-50 mt-1 w-56 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg py-1">
                    <p className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">{t('pref.title')}</p>
                    {quickHideOptions.map((o) => (
                      <button
                        key={`${o.type}:${o.value}`}
                        onClick={(e) => handleHide(o, e)}
                        className="w-full text-left px-3 py-1.5 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 truncate"
                      >
                        {o.label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
          <div className="hidden sm:flex items-center gap-1">
            {pinned && (
              <span className="flex items-center gap-1 bg-indigo-100 dark:bg-indigo-900/40 text-indigo-800 dark:text-indigo-300 text-xs font-medium px-2 py-1 rounded">
                <Pin className="w-3 h-3" />
                {t('paper.top')}
              </span>
            )}
            {isTrending && (
              <span className="flex items-center gap-1 bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-300 text-xs font-medium px-2 py-1 rounded">
                <TrendingUp className="w-3 h-3" />
                {t('paper.trending')}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Mobile badges */}
      <div className="flex sm:hidden items-center gap-1.5 mb-2">
        {pinned && (
          <span className="flex items-center gap-0.5 bg-indigo-100 dark:bg-indigo-900/40 text-indigo-800 dark:text-indigo-300 text-xs font-medium px-1.5 py-0.5 rounded">
            <Pin className="w-3 h-3" />
            {t('paper.top')}
          </span>
        )}
        {isTrending && (
          <span className="flex items-center gap-0.5 bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-300 text-xs font-medium px-1.5 py-0.5 rounded">
            <TrendingUp className="w-3 h-3" />
            {t('paper.trending')}
          </span>
        )}
      </div>

      {paper.abstract && (
        <p className="text-gray-600 dark:text-gray-400 text-sm mb-2 sm:mb-3 line-clamp-2">
          {paper.abstract}
        </p>
      )}

      {paper.authors && paper.authors.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 mb-2 sm:mb-3">
          <span className="text-xs text-gray-400 dark:text-gray-500 mr-1">{t('paper.authorsLabel')}</span>
          {paper.authors.slice(0, 3).map((author, index) => (
            <button
              key={index}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                router.push(`/author/${encodeURIComponent(author.trim())}`);
              }}
              className="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-800 dark:hover:text-primary-300 hover:underline bg-primary-50 dark:bg-primary-900/30 hover:bg-primary-100 dark:hover:bg-primary-900/50 px-1.5 py-0.5 rounded transition-colors"
            >
              {author.trim()}
            </button>
          ))}
          {paper.authors.length > 3 && (
            <span className="text-xs text-gray-400 dark:text-gray-500">{t('paper.etAl', { n: paper.authors.length })}</span>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-1.5 sm:gap-2 mb-2 sm:mb-3">
        {paper.topic && paper.topic !== 'Other' && (
          <span className={`text-xs font-medium px-1.5 sm:px-2 py-0.5 sm:py-1 rounded ${topicColors[paper.topic] || 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'}`}>
            {paper.topic}
          </span>
        )}
        {paper.economics_subfield && (
          <span className={`text-xs font-medium px-1.5 sm:px-2 py-0.5 sm:py-1 rounded ${subfieldColors[paper.economics_subfield] || 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'}`}>
            {paper.economics_subfield}
          </span>
        )}
        {paper.cnki_subject && paper.cnki_subject.split(';').filter(Boolean).slice(0, 2).map((subject, idx) => (
          <span key={idx} className="text-xs font-medium px-1.5 sm:px-2 py-0.5 sm:py-1 rounded bg-teal-100 dark:bg-teal-900/40 text-teal-800 dark:text-teal-300">
            {subject.trim()}
          </span>
        ))}
        {paper.cnki_subject && paper.cnki_subject.split(';').filter(Boolean).length > 2 && (
          <span className="text-xs text-gray-400 dark:text-gray-500">+{paper.cnki_subject.split(';').filter(Boolean).length - 2}</span>
        )}
        {paper.keywords_cn?.slice(0, 2).map((keyword, index) => (
          <button
            key={index}
            onClick={(e) => {
              e.preventDefault();
              router.push(`/search?search=${encodeURIComponent(keyword)}&search_field=keyword`);
            }}
            className="bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs px-1.5 sm:px-2 py-0.5 sm:py-1 rounded hover:bg-primary-100 dark:hover:bg-primary-900/50 hover:text-primary-700 dark:hover:text-primary-400 transition-colors cursor-pointer"
          >
            {keyword}
          </button>
        ))}
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-0 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
        <div className="flex items-center gap-2 sm:gap-4 flex-wrap">
          <span className="flex items-center gap-1">
            <Calendar className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
            {getIssuePeriod(paper.doi, paper.published_at, paper.journal_issue) || 'Unknown'}
          </span>
          <span className="bg-gray-100 dark:bg-gray-700 px-1.5 sm:px-2 py-0.5 sm:py-1 rounded text-xs">
            {paper.source}
          </span>
          {paper.venue && (
            <span className="bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400 px-1.5 sm:px-2 py-0.5 sm:py-1 rounded text-xs hidden sm:inline">
              {paper.venue}
            </span>
          )}
          {paper.journal_name && (
            <button
              onClick={() => router.push(`/search?journal=${encodeURIComponent(paper.journal_name!)}`)}
              className="bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 px-1.5 sm:px-2 py-0.5 sm:py-1 rounded text-xs hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors cursor-pointer truncate max-w-[120px] sm:max-w-none"
            >
              {paper.journal_name}
            </button>
          )}
        </div>
        <div className="flex items-center justify-between sm:justify-end gap-2 w-full sm:w-auto">
          <div className="flex items-center gap-1">
            <div className="w-12 sm:w-16 bg-gray-200 dark:bg-gray-600 rounded-full h-1.5 sm:h-2">
              <div
                className="bg-primary-600 h-1.5 sm:h-2 rounded-full"
                style={{ width: `${score * 100}%` }}
              />
            </div>
            <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
              {(score * 100).toFixed(0)}%
            </span>
          </div>
          <a
            href={paper.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 p-1"
          >
            <ExternalLink className="w-4 h-4 sm:w-5 sm:h-5" />
          </a>
        </div>
      </div>
    </div>
  );
}

export default memo(PaperCardInner);
