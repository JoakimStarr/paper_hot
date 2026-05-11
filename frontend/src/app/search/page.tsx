'use client';

import React, { useState, useEffect, useCallback, useRef, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Layout from '@/components/Layout';
import SearchBar from '@/components/SearchBar';
import PaperCard from '@/components/PaperCard';
import Pagination from '@/components/Pagination';
import SkeletonCard from '@/components/SkeletonCard';
import { papersApi } from '@/lib/api';
import { PaperCardListResponse, PaperCard as PaperCardType } from '@/types/paper';
import { Loader2, Search, ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { useLanguage } from '@/contexts/LanguageContext';
import { getCache, setCache, buildCacheKey } from '@/lib/cache';

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

  const initialSearch = searchParams.get('search') || '';
  const initialField = searchParams.get('search_field') || 'keyword';
  const initialJournal = searchParams.get('journal') || '';

  const [papers, setPapers] = useState<PaperCardType[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [queryKey, setQueryKey] = useState(0);
  const [pageSize, setPageSize] = useState(20);

  const [currentSearch, setCurrentSearch] = useState(initialSearch);
  const [currentField, setCurrentField] = useState(initialField);
  const [currentJournal, setCurrentJournal] = useState(initialJournal);

  useEffect(() => {
    const s = searchParams.get('search') || '';
    const f = searchParams.get('search_field') || 'keyword';
    const j = searchParams.get('journal') || '';
    setCurrentSearch(s);
    setCurrentField(f);
    setCurrentJournal(j);
    setPage(1);
    setQueryKey(k => k + 1);
  }, [searchParams]);

  const buildParams = useCallback((p: number) => ({
    page: p,
    page_size: pageSize,
    search: currentSearch || undefined,
    search_field: currentField || undefined,
    journal_name: currentJournal || undefined,
    sort_by: 'date',
    sort_order: 'desc',
  }), [currentSearch, currentField, currentJournal, pageSize]);

  useEffect(() => {
    let cancelled = false;

    const loadPage = async () => {
      if (!currentSearch && !currentJournal) {
        setPapers([]);
        setTotal(0);
        setTotalPages(0);
        setLoading(false);
        return;
      }

      setLoading(true);
      try {
        const params = buildParams(page);
        const cacheKey = buildCacheKey(params as Record<string, unknown>);
        let response = getCache<PaperCardListResponse>(cacheKey);

        if (!response) {
          response = await papersApi.getPapers(params);
          setCache(cacheKey, response);
        }

        if (!cancelled) {
          setPapers(response.papers);
          setTotal(response.total);
          setTotalPages(Math.ceil(response.total / pageSize));
        }
      } catch (error) {
        console.error('Error searching papers:', error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadPage();
    return () => { cancelled = true; };
  }, [page, queryKey]);

  const handleSearch = (query: string, field: string) => {
    const params = new URLSearchParams();
    params.set('search', query);
    params.set('search_field', field);
    router.push(`/search?${params.toString()}`);
  };

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return;
    setPage(newPage);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setPage(1);
  };

  const hasParams = currentSearch || currentJournal;

  return (
    <Layout>
      <div className="mb-6">
        <Link href="/" className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-primary-600 transition-colors mb-4">
          <ArrowLeft className="w-5 h-5" />
          <span>{t('home.previous')}</span>
        </Link>

        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-4">搜索论文</h1>

        <SearchBar
          initialQuery={currentSearch}
          initialField={currentField}
          onSearch={handleSearch}
        />

        {currentJournal && (
          <div className="mt-3 flex items-center gap-2">
            <span className="text-sm text-gray-500 dark:text-gray-400">期刊筛选：</span>
            <span className="bg-blue-50 dark:bg-blue-900/30 text-blue-700 px-2 py-1 rounded text-xs">
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
        <div className="grid grid-cols-1 gap-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : hasParams ? (
        <>
          <div className="mb-4 text-sm text-gray-500 dark:text-gray-400">
            {total > 0 ? `找到 ${total} 篇论文` : '未找到符合条件的论文'}
          </div>

          <div className="grid grid-cols-1 gap-6">
            {papers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} />
            ))}
          </div>

          {papers.length === 0 && (
            <div className="text-center py-12">
              <Search className="w-12 h-12 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-600 dark:text-gray-400 mb-4">未找到符合条件的论文</p>
              <Link href="/" className="text-primary-600 hover:underline">
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
        <div className="text-center py-12">
          <Search className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 dark:text-gray-400 text-lg mb-2">输入关键词开始搜索</p>
          <p className="text-gray-400 text-sm">支持按关键词、标题搜索，也支持期刊筛选</p>
        </div>
      )}
    </Layout>
  );
}