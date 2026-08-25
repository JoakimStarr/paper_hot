'use client';

import React, { useCallback, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Layout from '@/components/Layout';
import SearchBar from '@/components/SearchBar';
import PaperCard from '@/components/PaperCard';
import Pagination from '@/components/Pagination';
import SkeletonCard from '@/components/SkeletonCard';
import { Loader2, Search, ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { useLanguage } from '@/contexts/LanguageContext';
import { usePapersPage } from '@/lib/usePapersPage';

export default function SearchPage() {
  return (
    <Suspense fallback={
      <Layout>
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      </Layout>
    }>
      <SearchPageInner />
    </Suspense>
  );
}

function SearchPageInner() {
  const { t } = useLanguage();
  const searchParams = useSearchParams();
  const router = useRouter();

  const currentSearch = searchParams.get('search') || '';
  const currentField = searchParams.get('search_field') || 'keyword';
  const currentJournal = searchParams.get('journal') || '';

  const buildParams = useCallback((p: number, pageSize: number) => ({
    page: p,
    page_size: pageSize,
    search: currentSearch || undefined,
    search_field: currentField || undefined,
    journal_name: currentJournal || undefined,
    sort_by: 'date',
    sort_order: 'desc',
  }), [currentSearch, currentField, currentJournal]);

  // 数据流收敛在 lib/usePapersPage.ts（与首页共用）；无搜索词/期刊时禁用请求
  const {
    papers, loading, total, totalPages,
    page, pageSize, handlePageChange, handlePageSizeChange,
  } = usePapersPage({
    buildParams,
    deps: [currentSearch, currentField, currentJournal],
    enabled: !!(currentSearch || currentJournal),
  });

  const handleSearch = (query: string, field: string) => {
    const params = new URLSearchParams();
    params.set('search', query);
    params.set('search_field', field);
    router.push(`/search?${params.toString()}`);
  };

  const hasParams = currentSearch || currentJournal;

  return (
    <Layout>
      <div className="mb-4 sm:mb-6">
        <Link href="/" className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-primary-600 transition-colors mb-3 sm:mb-4">
          <ArrowLeft className="w-5 h-5" />
          <span className="text-sm sm:text-base">{t('home.previous')}</span>
        </Link>

        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white mb-3 sm:mb-4">搜索论文</h1>

        <SearchBar
          initialQuery={currentSearch}
          initialField={currentField}
          onSearch={handleSearch}
        />

        {currentJournal && (
          <div className="mt-2 sm:mt-3 flex items-center gap-2">
            <span className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">期刊筛选：</span>
            <span className="bg-blue-50 dark:bg-blue-900/30 text-blue-700 px-2 py-1 rounded text-xs truncate max-w-[150px] sm:max-w-none">
              {currentJournal}
            </span>
            <button
              onClick={() => router.push('/search')}
              className="text-xs text-gray-400 hover:text-gray-600 dark:text-gray-400"
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:gap-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : hasParams ? (
        <>
          <div className="mb-3 sm:mb-4 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            {total > 0 ? `找到 ${total} 篇论文` : '未找到符合条件的论文'}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:gap-6">
            {papers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} />
            ))}
          </div>

          {papers.length === 0 && (
            <div className="text-center py-8 sm:py-12">
              <Search className="w-10 h-10 sm:w-12 sm:h-12 text-gray-300 mx-auto mb-3 sm:mb-4" />
              <p className="text-gray-600 dark:text-gray-400 mb-3 sm:mb-4 text-sm sm:text-base">未找到符合条件的论文</p>
              <Link href="/" className="text-primary-600 hover:underline text-sm sm:text-base">
                返回首页
              </Link>
            </div>
          )}

          {total > 0 && (
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              totalItems={total}
              pageSize={pageSize}
              onPageChange={handlePageChange}
              onPageSizeChange={handlePageSizeChange}
            />
          )}
        </>
      ) : (
        <div className="text-center py-8 sm:py-12">
          <Search className="w-12 h-12 sm:w-16 sm:h-16 text-gray-300 mx-auto mb-3 sm:mb-4" />
          <p className="text-gray-500 dark:text-gray-400 text-base sm:text-lg mb-2">输入关键词开始搜索</p>
          <p className="text-gray-400 text-xs sm:text-sm">支持按关键词、标题搜索，也支持期刊筛选</p>
        </div>
      )}
    </Layout>
  );
}
