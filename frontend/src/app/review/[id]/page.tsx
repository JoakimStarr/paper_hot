'use client';

import React, { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import Layout from '@/components/Layout';
import { Loader2, ArrowLeft, BookMarked } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { usePageTitle } from '@/lib/usePageTitle';
import { producerApi } from '@/lib/api';
import type { ReviewDetail } from '@/lib/api';

const MarkdownRenderer = dynamic(() => import('@/components/MarkdownRenderer'), {
  ssr: false,
  loading: () => <div className="text-sm text-gray-400 py-4">…</div>,
});

/** 文献综述详情页：工作台「最近文献综述」的深链落点。 */
export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params?.id);
  const { t } = useLanguage();
  usePageTitle(t('dash.reviewTitle'));
  const [data, setData] = useState<ReviewDetail | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    producerApi.getReview(id)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, [id]);

  return (
    <Layout>
      <div className="mb-6">
        <Link
          href="/dashboard?tab=stack"
          className="inline-flex items-center gap-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline mb-3"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          {t('dash.reviewBack')}
        </Link>
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white mb-1">{t('dash.reviewTitle')}</h1>
      </div>

      {error ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">{t('dash.reviewLoadFailed')}</p>
      ) : !data ? (
        <p className="text-sm text-gray-400">
          <Loader2 className="w-4 h-4 animate-spin inline-block mr-1" />
          {t('dash.watchNewLoading')}
        </p>
      ) : (
        <article className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
          <div className="flex items-start gap-2 mb-4 pb-4 border-b border-gray-100 dark:border-gray-700">
            <BookMarked className="w-5 h-5 text-purple-500 shrink-0 mt-0.5" />
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">{data.topic}</h2>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-400">
                {data.created_at && <span>{t('dash.reviewGeneratedAt', { d: new Date(data.created_at).toLocaleDateString() })}</span>}
                {Array.isArray(data.papers) && <span>{t('dash.reviewPapers', { n: data.papers.length })}</span>}
              </div>
            </div>
          </div>
          {data.status === 'failed' || !data.content ? (
            <p className="text-sm text-gray-400">{t('dash.noData')}</p>
          ) : (
            <MarkdownRenderer content={data.content} />
          )}
        </article>
      )}
    </Layout>
  );
}
