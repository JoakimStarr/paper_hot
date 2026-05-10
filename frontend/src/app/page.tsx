'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import Filters from '@/components/Filters';
import Pagination from '@/components/Pagination';
import { papersApi } from '@/lib/api';
import { PaperCardListResponse, PaperCard as PaperCardType } from '@/types/paper';
import { Loader2 } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { getCache, setCache, buildCacheKey } from '@/lib/cache';

const PAGE_SIZE = 20;
const INITIAL_PREFETCH = 3;

export default function HomePage() {
  const { t } = useLanguage();
  const [papers, setPapers] = useState<PaperCardType[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [queryKey, setQueryKey] = useState(0);
  const pageCache = useRef<Map<number, PaperCardType[]>>(new Map());
  const fetchedTotalRef = useRef<number>(0);
  const prefetchedRef = useRef(false);

  const [minScore, setMinScore] = useState<number | null>(null);
  const [selectedDiscipline, setSelectedDiscipline] = useState<string | null>(null);
  const [selectedJournal, setSelectedJournal] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [searchField, setSearchField] = useState('');
  const [sortBy, setSortBy] = useState('date');
  const [sortOrder, setSortOrder] = useState('desc');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flushSearch = useCallback((value: string) => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    setDebouncedSearch(value);
  }, []);

  useEffect(() => {
    debounceRef.current = setTimeout(() => setDebouncedSearch(searchQuery), 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchQuery]);

  useEffect(() => {
    setPage(1);
    pageCache.current.clear();
    prefetchedRef.current = false;
    setQueryKey(k => k + 1);
  }, [debouncedSearch, searchField, sortBy, sortOrder, minScore, selectedDiscipline, selectedJournal]);

  const buildParams = useCallback((p: number) => ({
    page: p,
    page_size: PAGE_SIZE,
    min_score: minScore || undefined,
    discipline: selectedDiscipline || undefined,
    journal_name: selectedJournal || undefined,
    search: debouncedSearch || undefined,
    search_field: searchField || undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
  }), [minScore, selectedDiscipline, selectedJournal, debouncedSearch, searchField, sortBy, sortOrder]);

  const applyResponse = useCallback((response: PaperCardListResponse, p: number) => {
    setPapers(response.papers);
    setTotal(response.total);
    setTotalPages(Math.ceil(response.total / PAGE_SIZE));
    setPage(p);
    pageCache.current.set(p, response.papers);
    fetchedTotalRef.current = response.total;
  }, []);

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
          setTotalPages(Math.ceil(fetchedTotalRef.current / PAGE_SIZE));
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
        const pagesLeft = Math.min(INITIAL_PREFETCH, Math.ceil(fetchedTotalRef.current / PAGE_SIZE));
        for (let p = 2; p <= pagesLeft; p++) {
          fetchPage(p).catch(() => {});
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
        selectedDiscipline={selectedDiscipline}
        selectedJournal={selectedJournal}
        searchQuery={searchQuery}
        searchField={searchField}
        sortBy={sortBy}
        sortOrder={sortOrder}
        onMinScoreChange={(v) => setMinScore(v)}
        onDisciplineChange={(v) => setSelectedDiscipline(v)}
        onJournalChange={(v) => setSelectedJournal(v)}
        onSearchChange={(v) => setSearchQuery(v)}
        onSearchSubmit={(v) => flushSearch(v)}
        onSearchFieldChange={(v) => setSearchField(v)}
        onSortByChange={(v) => setSortBy(v)}
        onSortOrderToggle={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
      />

      {loading ? (
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-6">
            {papers.map((paper) => (
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
              totalPages={totalPages}
              totalItems={total}
              pageSize={PAGE_SIZE}
              onPageChange={handlePageChange}
            />
          )}
        </>
      )}
    </Layout>
  );
}