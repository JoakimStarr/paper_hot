'use client';

import React, { useState, useEffect, useCallback, useRef, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import Filters from '@/components/Filters';
import Pagination from '@/components/Pagination';
import SkeletonCard from '@/components/SkeletonCard';
import { papersApi } from '@/lib/api';
import { PaperCardListResponse, PaperCard as PaperCardType } from '@/types/paper';
import { Loader2 } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { getCache, setCache, buildCacheKey, getBookmarks } from '@/lib/cache';

const INITIAL_PREFETCH = 3;

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
  const [papers, setPapers] = useState<PaperCardType[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [queryKey, setQueryKey] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const pageCache = useRef<Map<number, PaperCardType[]>>(new Map());
  const fetchedTotalRef = useRef<number>(0);
  const prefetchedRef = useRef(false);

  const [minScore, setMinScore] = useState<number | null>(null);
  const [selectedTopic, setSelectedTopic] = useState<string[]>([]);
  const [selectedJournal, setSelectedJournal] = useState<string[]>([]);
  const [showBookmarksOnly, setShowBookmarksOnly] = useState(false);

  const [sortBy, setSortBy] = useState('date');
  const [sortOrder, setSortOrder] = useState('desc');

  useEffect(() => {
    const journal = searchParams.get('journal');
    if (journal) setSelectedJournal([journal]);
  }, []);

  useEffect(() => {
    setPage(1);
    pageCache.current.clear();
    prefetchedRef.current = false;
    setQueryKey(k => k + 1);
  }, [sortBy, sortOrder, minScore, selectedTopic, selectedJournal, pageSize]);

  const buildParams = useCallback((p: number) => ({
    page: p,
    page_size: pageSize,
    min_score: minScore || undefined,
    economics_subfield: selectedTopic.length > 0 ? selectedTopic.join(',') : undefined,
    journal_name: selectedJournal.length > 0 ? selectedJournal.join(',') : undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
  }), [minScore, selectedTopic, selectedJournal, sortBy, sortOrder, pageSize]);

  const applyResponse = useCallback((response: PaperCardListResponse, p: number) => {
    setPapers(response.papers);
    setTotal(response.total);
    setTotalPages(Math.ceil(response.total / pageSize));
    setPage(p);
    pageCache.current.set(p, response.papers);
    fetchedTotalRef.current = response.total;
  }, [pageSize]);

  const fetchPage = useCallback(async (p: number) => {
    const params = buildParams(p);
    const cacheKey = buildCacheKey(params as Record<string, unknown>);
    const cached = getCache<PaperCardListResponse>(cacheKey);

    if (cached) {
      pageCache.current.set(p, cached.papers);
      fetchedTotalRef.current = cached.total;
      return cached;
    }

    const response = await papersApi.getPapers(params);
    setCache(cacheKey, response);
    pageCache.current.set(p, response.papers);
    fetchedTotalRef.current = response.total;
    return response;
  }, [buildParams]);

  useEffect(() => {
    let cancelled = false;

    const loadPage = async () => {
      setLoading(true);

      const cached = pageCache.current.get(page);
      if (cached) {
        if (!cancelled) {
          setPapers(cached);
          setTotal(fetchedTotalRef.current);
          setTotalPages(Math.ceil(fetchedTotalRef.current / pageSize));
          setLoading(false);
        }
        return;
      }

      try {
        const response = await fetchPage(page);
        if (!cancelled) {
          applyResponse(response, page);
        }
      } catch (error) {
        console.error('Error fetching papers:', error);
      } finally {
        if (!cancelled) setLoading(false);
      }

      if (page === 1 && !prefetchedRef.current && !cancelled) {
        prefetchedRef.current = true;
        const pagesLeft = Math.min(INITIAL_PREFETCH, Math.ceil(fetchedTotalRef.current / pageSize));
        if (pagesLeft >= 3) {
          Promise.all([
            fetchPage(2).catch(() => {}),
            fetchPage(3).catch(() => {}),
          ]);
        } else {
          for (let p = 2; p <= pagesLeft; p++) {
            fetchPage(p).catch(() => {});
          }
        }
      }
    };

    loadPage();
    return () => { cancelled = true; };
  }, [page, queryKey]);

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return;
    setPage(newPage);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setPage(1);
    pageCache.current.clear();
  };

  const displayedPapers = showBookmarksOnly
    ? papers.filter(p => getBookmarks().includes(p.id))
    : papers;
  const displayedTotal = showBookmarksOnly ? displayedPapers.length : total;
  const displayedTotalPages = showBookmarksOnly ? Math.ceil(displayedPapers.length / pageSize) : totalPages;

  const pagedPapers = showBookmarksOnly
    ? displayedPapers.slice((page - 1) * pageSize, page * pageSize)
    : papers;

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900 mb-1">
          {t('home.title')}
        </h1>
        <p className="text-gray-500 text-sm">
          {t('home.subtitle')}
        </p>
      </div>

      <Filters
        minScore={minScore}
        selectedTopic={selectedTopic}
        selectedJournal={selectedJournal}
        sortBy={sortBy}
        sortOrder={sortOrder}
        showBookmarksOnly={showBookmarksOnly}
        onMinScoreChange={(v) => setMinScore(v)}
        onTopicChange={(v) => setSelectedTopic(v)}
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
            {pagedPapers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} />
            ))}
          </div>

          {papers.length === 0 && (
            <div className="text-center py-12">
              <p className="text-gray-600">{t('home.noPapers')}</p>
            </div>
          )}

          {total > 0 && (
            <Pagination
              currentPage={page}
              totalPages={showBookmarksOnly ? displayedTotalPages : totalPages}
              totalItems={showBookmarksOnly ? displayedTotal : total}
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