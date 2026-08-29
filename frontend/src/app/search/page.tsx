'use client';

import React, { useCallback, useMemo, Suspense, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Layout from '@/components/Layout';
import SearchBar from '@/components/SearchBar';
import Filters from '@/components/Filters';
import PaperCard from '@/components/PaperCard';
import Pagination from '@/components/Pagination';
import SkeletonCard from '@/components/SkeletonCard';
import { Loader2, Search, ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { useLanguage } from '@/contexts/LanguageContext';
import { usePageTitle } from '@/lib/usePageTitle';
import { usePapersPage } from '@/lib/usePapersPage';
import { usePreferences } from '@/lib/usePreferences';

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
  usePageTitle(t('nav.search'));
  const searchParams = useSearchParams();
  const router = useRouter();

  // 与首页同套筛选器（P1-9）：评分/子领域/专题/期刊/排序
  const [minScore, setMinScore] = useState<number | null>(null);
  const [selectedSubfield, setSelectedSubfield] = useState<string[]>([]);
  const [selectedCnkiSubject, setSelectedCnkiSubject] = useState<string[]>([]);
  const [selectedJournal, setSelectedJournal] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState('date');
  const [sortOrder, setSortOrder] = useState('desc');

  // 「不感兴趣」屏蔽版本号：新增/删除屏蔽项时列表需重取（后端已在列表层过滤）
  const { version: prefVersion } = usePreferences();

  const currentSearch = searchParams.get('search') || '';
  const currentFieldParam = searchParams.get('search_field');
  const urlJournal = searchParams.get('journal') || '';
  const currentField = currentFieldParam || 'all';

  // 用 useMemo 稳定引用：否则每帧生成新数组，会被 usePapersPage 的 deps 判定为变化，
  // 触发 queryKey 无限 bump → 列表不停重拉重渲（表现为页面卡顿）。
  const activeJournals = useMemo(
    () => selectedJournal.length > 0
      ? selectedJournal
      : urlJournal ? [urlJournal] : [],
    [selectedJournal, urlJournal],
  );

  const buildParams = useCallback((p: number, pageSize: number) => ({
    page: p,
    page_size: pageSize,
    search: currentSearch || undefined,
    search_field: currentField || undefined,
    journal_name: activeJournals.length > 0 ? activeJournals.join(',') : undefined,
    min_score: minScore || undefined,
    economics_subfield: selectedSubfield.length > 0 ? selectedSubfield.join(',') : undefined,
    cnki_subject: selectedCnkiSubject.length > 0 ? selectedCnkiSubject.join(',') : undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
  }), [currentSearch, currentField, activeJournals, minScore, selectedSubfield, selectedCnkiSubject, sortBy, sortOrder]);

  // 数据流收敛在 lib/usePapersPage.ts（与首页共用）；无搜索词/期刊时禁用请求
  const {
    papers, loading, total, totalPages,
    page, pageSize, handlePageChange, handlePageSizeChange,
  } = usePapersPage({
    buildParams,
    deps: [currentSearch, currentField, activeJournals, minScore, selectedSubfield, selectedCnkiSubject, sortBy, sortOrder, prefVersion],
    cacheBust: prefVersion,
    enabled: !!(currentSearch || activeJournals.length > 0),
  });

  const handleSearch = (query: string, field: string) => {
    const params = new URLSearchParams();
    params.set('search', query);
    if (field && field !== 'all') params.set('search_field', field);
    router.push(`/search?${params.toString()}`);
  };

  const hasParams = currentSearch || activeJournals.length > 0;

  return (
    <Layout>
      <div className="mb-4 sm:mb-6">
        <Link href="/" className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-primary-600 transition-colors mb-3 sm:mb-4">
          <ArrowLeft className="w-5 h-5" />
          <span className="text-sm sm:text-base">{t('nav.backHome')}</span>
        </Link>

        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white mb-3 sm:mb-4">研究级检索</h1>

        <SearchBar
          initialQuery={currentSearch}
          initialField={currentField}
          onSearch={handleSearch}
        />

        {/* 高级语法提示（P1-9） */}
        <p className="mt-2 text-xs text-gray-400 dark:text-gray-500 leading-relaxed">
          高级语法：多词默认 AND；<code className="px-1 bg-gray-100 dark:bg-gray-700 rounded">OR</code> 连接可选词；
          <code className="px-1 bg-gray-100 dark:bg-gray-700 rounded mx-0.5">NOT</code> 排除；
          <code className="px-1 bg-gray-100 dark:bg-gray-700 rounded">&quot;精确短语&quot;</code> 匹配标题/摘要；
          <code className="px-1 bg-gray-100 dark:bg-gray-700 rounded ml-0.5">author:姓名</code> 按作者检索（字段选&quot;全部&quot;时生效）
        </p>

        {activeJournals.length > 0 && !selectedJournal.length && (
          <div className="mt-2 sm:mt-3 flex items-center gap-2">
            <span className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">期刊筛选：</span>
            <span className="bg-blue-50 dark:bg-blue-900/30 text-blue-700 px-2 py-1 rounded text-xs truncate max-w-[150px] sm:max-w-none">
              {activeJournals[0]}
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

      <Filters
        minScore={minScore}
        selectedSubfield={selectedSubfield}
        selectedCnkiSubject={selectedCnkiSubject}
        selectedJournal={selectedJournal}
        sortBy={sortBy}
        sortOrder={sortOrder}
        hideBookmarksFilter
        showBookmarksOnly={false}
        onMinScoreChange={(v) => setMinScore(v)}
        onSubfieldChange={(v) => setSelectedSubfield(v)}
        onCnkiSubjectChange={(v) => setSelectedCnkiSubject(v)}
        onJournalChange={(v) => {
          setSelectedJournal(v);
          if (urlJournal && v.length === 0) router.push('/search');
        }}
        onSortByChange={(v) => setSortBy(v)}
        onSortOrderToggle={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
        onBookmarksChange={() => {}}
      />

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
          <p className="text-gray-400 text-xs sm:text-sm">支持高级语法、按相关度排序，也可用下方筛选器缩小范围</p>
        </div>
      )}
    </Layout>
  );
}
