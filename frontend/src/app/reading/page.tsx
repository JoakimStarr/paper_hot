'use client';

import React, { useEffect, useState } from 'react';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import { History, BookOpen } from 'lucide-react';
import Link from 'next/link';
import { useLanguage } from '@/contexts/LanguageContext';
import { personalApi } from '@/lib/api';
import { PaperCard as PaperCardType } from '@/types/paper';

export default function ReadingHistoryPage() {
  const { t } = useLanguage();
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
          <div className="grid grid-cols-1 gap-4 sm:gap-6">
            {papers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} read />
            ))}
          </div>
        </>
      )}
    </Layout>
  );
}