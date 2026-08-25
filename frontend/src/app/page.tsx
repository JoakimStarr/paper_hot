'use client';

import React, { useState, useEffect, useCallback, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import Filters from '@/components/Filters';
import Pagination from '@/components/Pagination';
import SkeletonCard from '@/components/SkeletonCard';
import { Loader2, Search } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { getBookmarks } from '@/lib/cache';
import { usePapersPage } from '@/lib/usePapersPage';

export default function HomePage() {
  return (
    <Suspense fallback={
      <Layout>
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      </Layout>
    }>
      <HomePageInner />
    </Suspense>
  );
}

function HomePageInner() {
  const { t } = useLanguage();
  const searchParams = useSearchParams();
  const router = useRouter();

  const [minScore, setMinScore] = useState<number | null>(null);
  const [selectedSubfield, setSelectedSubfield] = useState<string[]>([]);
  const [selectedCnkiSubject, setSelectedCnkiSubject] = useState<string[]>([]);
  const [selectedJournal, setSelectedJournal] = useState<string[]>([]);
  const [showBookmarksOnly, setShowBookmarksOnly] = useState(false);
  const [sortBy, setSortBy] = useState('date');
  const [sortOrder, setSortOrder] = useState('desc');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    const journal = searchParams.get('journal');
    if (journal) setSelectedJournal([journal]);
  }, [searchParams]);

  const buildParams = useCallback((p: number, pageSize: number) => ({
    page: p,
    page_size: pageSize,
    min_score: minScore || undefined,
    economics_subfield: selectedSubfield.length > 0 ? selectedSubfield.join(',') : undefined,
    cnki_subject: selectedCnkiSubject.length > 0 ? selectedCnkiSubject.join(',') : undefined,
    journal_name: selectedJournal.length > 0 ? selectedJournal.join(',') : undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
  }), [minScore, selectedSubfield, selectedCnkiSubject, selectedJournal, sortBy, sortOrder]);

  // 数据流收敛在 lib/usePapersPage.ts（与搜索页共用），首页额外启用 3 页预取
  const {
    papers, loading, total, totalPages,
    page, pageSize, handlePageChange, handlePageSizeChange,
  } = usePapersPage({
    buildParams,
    deps: [sortBy, sortOrder, minScore, selectedSubfield, selectedCnkiSubject, selectedJournal],
    prefetch: 3,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchQuery.trim();
    if (q) {
      // 搜索页读取的参数名是 search（q 会导致搜索框跳转后显示空闲状态）
      router.push(`/search?search=${encodeURIComponent(q)}`);
    }
  };

  // 收藏过滤：仅对当前页内存中的论文筛选（分页基于服务端 total，书签视图为本地子集）
  const displayedPapers = showBookmarksOnly
    ? papers.filter(p => getBookmarks().includes(p.id))
    : papers;
  const displayedTotalPages = showBookmarksOnly
    ? Math.max(1, Math.ceil(displayedPapers.length / pageSize))
    : totalPages;

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
          {t('home.title')}
        </h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mb-4">
          {t('home.subtitle')}
        </p>
        <form onSubmit={handleSearch} className="relative max-w-xl">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索论文标题、作者、关键词..."
            className="w-full pl-10 pr-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none transition-shadow text-sm"
          />
        </form>
      </div>

      <Filters
        minScore={minScore}
        selectedSubfield={selectedSubfield}
        selectedCnkiSubject={selectedCnkiSubject}
        selectedJournal={selectedJournal}
        sortBy={sortBy}
        sortOrder={sortOrder}
        showBookmarksOnly={showBookmarksOnly}
        onMinScoreChange={(v) => setMinScore(v)}
        onSubfieldChange={(v) => setSelectedSubfield(v)}
        onCnkiSubjectChange={(v) => setSelectedCnkiSubject(v)}
        onJournalChange={(v) => setSelectedJournal(v)}
        onSortByChange={(v) => setSortBy(v)}
        onSortOrderToggle={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
        onBookmarksChange={(v) => setShowBookmarksOnly(v)}
      />

      {loading ? (
        <div className="grid grid-cols-1 gap-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-6">
            {displayedPapers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} />
            ))}
          </div>

          {papers.length === 0 && (
            <div className="text-center py-12">
              <p className="text-gray-600 dark:text-gray-400">{t('home.noPapers')}</p>
            </div>
          )}

          {total > 0 && (
            <Pagination
              currentPage={page}
              totalPages={displayedTotalPages}
              totalItems={displayedPapers.length}
              pageSize={pageSize}
              onPageChange={handlePageChange}
              onPageSizeChange={handlePageSizeChange}
            />
          )}
        </>
      )}
    </Layout>
  );
}
