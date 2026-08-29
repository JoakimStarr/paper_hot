'use client';

import React, { useEffect, useState } from 'react';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import { History, BookOpen } from 'lucide-react';
import Link from 'next/link';
import { useLanguage } from '@/contexts/LanguageContext';
import { usePageTitle } from '@/lib/usePageTitle';
import { personalApi } from '@/lib/api';
import { PaperCard as PaperCardType } from '@/types/paper';

export default function ReadingHistoryPage() {
  const { t } = useLanguage();
  usePageTitle(t('nav.reading'));
  const [papers, setPapers] = useState<PaperCardType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    let cancelled = false;
    personalApi.getReadingHistory()
      .then((res) => {
        if (cancelled) return;
        setPapers(res.papers || []);
        setTotal(res.total || 0);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) { setError(true); setLoading(false); }
      });
    return () => { cancelled = true; };
  }, []);

  // 时间分组：今天 / 本周（近7天）/ 更早；组内保持接口返回的排序（阅读时间倒序）
  const groups = groupByTime(papers);

  return (
    <Layout>
      <div className="flex items-center justify-between mb-4 sm:mb-6">
        <h1 className="flex items-center gap-2 text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">
          <History className="w-5 h-5 sm:w-6 sm:h-6 text-primary-600 dark:text-primary-400" />
          {t('reading.title')}
        </h1>
        <Link href="/" className="text-sm text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
          {t('reading.back')}
        </Link>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:gap-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-6 h-32 animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="text-center py-12">
          <p className="text-red-500 text-sm sm:text-base mb-3">{t('reading.loadFailed')}</p>
          <Link href="/" className="text-primary-600 hover:underline text-sm">{t('reading.back')}</Link>
        </div>
      ) : papers.length === 0 ? (
        <div className="text-center py-12 sm:py-16">
          <BookOpen className="w-12 h-12 sm:w-16 sm:h-16 text-gray-300 mx-auto mb-3 sm:mb-4" />
          <p className="text-gray-600 dark:text-gray-400 mb-3 sm:mb-4">{t('reading.empty')}</p>
          <Link href="/" className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-600 text-white text-sm hover:bg-primary-700 transition-colors">
            <BookOpen className="w-4 h-4" />
            {t('reading.goBrowse')}
          </Link>
        </div>
      ) : (
        <>
          <div className="mb-3 sm:mb-4 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            {t('reading.count', { n: total })}
          </div>
          <div className="space-y-6 sm:space-y-8">
            {groups.map((group) => (
              <section key={group.key}>
                <h2 className="sticky top-16 z-10 -mx-1 px-1 py-1.5 mb-3 bg-gray-50/95 dark:bg-gray-900/95 backdrop-blur text-sm font-bold text-gray-700 dark:text-gray-200 border-b border-gray-200 dark:border-gray-700 transition-colors">
                  {group.label}
                  <span className="ml-1.5 font-normal text-xs text-gray-400 dark:text-gray-500">
                    {group.papers.length}
                  </span>
                </h2>
                <div className="grid grid-cols-1 gap-4 sm:gap-6">
                  {group.papers.map((paper) => (
                    <PaperCard key={paper.id} paper={paper} read />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </>
      )}
    </Layout>
  );
}

interface ReadingGroup {
  key: 'today' | 'week' | 'earlier';
  label: string;
  papers: PaperCardType[];
}

/** 按「今天 / 本周 / 更早」三组划分；时间取记录的 created_at（缺省回退 published_at），解析失败归入「更早」。 */
function groupByTime(papers: PaperCardType[]): ReadingGroup[] {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfWeek = startOfToday - 7 * 24 * 60 * 60 * 1000;
  const ts = (p: PaperCardType) =>
    Date.parse(p.created_at || '') || Date.parse(p.published_at || '') || 0;

  const groups: ReadingGroup[] = [
    { key: 'today', label: '今天', papers: [] },
    { key: 'week', label: '本周', papers: [] },
    { key: 'earlier', label: '更早', papers: [] },
  ];
  for (const p of papers) {
    const t = ts(p);
    if (t >= startOfToday) groups[0].papers.push(p);
    else if (t >= startOfWeek) groups[1].papers.push(p);
    else groups[2].papers.push(p);
  }
  return groups.filter((g) => g.papers.length > 0);
}