'use client';

/**
 * 论文分页列表的共享数据流 hook（首页 / 搜索页共用单一实现）。
 *
 * 统一承载：分页 state、sessionStorage 缓存、首页预取、翻页处理器。
 * 页面只需提供 buildParams（每页的请求参数）与 deps（筛选条件数组），
 * 渲染层（Filters / SearchBar 等差异 UI）留在各自页面。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { papersApi } from '@/lib/api';
import { PaperCard as PaperCardType, PaperCardListResponse } from '@/types/paper';
import { getCache, setCache, buildCacheKey } from '@/lib/cache';

interface UsePapersPageOptions {
  /** 构造第 p 页的请求参数（返回完整 params 对象） */
  buildParams: (page: number, pageSize: number) => Record<string, unknown>;
  /** 查询条件数组：任一变化时重置回第 1 页重新加载 */
  deps: unknown[];
  /** false 时不发请求并清空列表（如搜索页无关键词时） */
  enabled?: boolean;
  /** 首页加载后预取的后续页数（首屏翻页体验优化，默认 0 不预取） */
  prefetch?: number;
}

export function usePapersPage({
  buildParams,
  deps,
  enabled = true,
  prefetch = 0,
}: UsePapersPageOptions) {
  const [papers, setPapers] = useState<PaperCardType[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [queryKey, setQueryKey] = useState(0);
  const prefetchedRef = useRef(false);

  // buildParams 走 ref：筛选变化只触发 deps effect 重置分页，
  // 不把函数引用引入 fetchPage 依赖链，避免双请求竞态
  const buildParamsRef = useRef(buildParams);
  buildParamsRef.current = buildParams;

  // deps 变化 → 重置到第 1 页重新加载
  useEffect(() => {
    setPage(1);
    prefetchedRef.current = false;
    setQueryKey(k => k + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const fetchPage = useCallback(async (p: number) => {
    const params = buildParamsRef.current(p, pageSize);
    const cacheKey = buildCacheKey(params as Record<string, unknown>);
    let response = getCache<PaperCardListResponse>(cacheKey);
    if (!response) {
      response = await papersApi.getPapers(params);
      setCache(cacheKey, response);
    }
    return response;
  }, [pageSize]);

  useEffect(() => {
    let cancelled = false;

    const loadPage = async () => {
      if (!enabled) {
        setPapers([]);
        setTotal(0);
        setTotalPages(0);
        setLoading(false);
        return;
      }

      setLoading(true);
      try {
        const response = await fetchPage(page);
        if (!cancelled) {
          setPapers(response.papers);
          setTotal(response.total);
          setTotalPages(Math.ceil(response.total / pageSize));
        }

        // 首页预取后续 prefetch 页（静默，失败忽略）
        if (page === 1 && !prefetchedRef.current && !cancelled && prefetch > 0) {
          prefetchedRef.current = true;
          const maxPages = Math.ceil(response.total / pageSize);
          const end = Math.min(prefetch + 1, maxPages);
          for (let p = 2; p <= end; p++) {
            fetchPage(p).catch(() => {});
          }
        }
      } catch (error) {
        console.error('Error fetching papers:', error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadPage();
    return () => { cancelled = true; };
  }, [page, queryKey, pageSize, enabled, fetchPage, prefetch]);

  const handlePageChange = useCallback((newPage: number) => {
    if (newPage < 1) return;
    setPage(newPage);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const handlePageSizeChange = useCallback((size: number) => {
    setPageSize(size);
    setPage(1);
  }, []);

  return {
    papers, loading, total, totalPages,
    page, pageSize, handlePageChange, handlePageSizeChange,
  };
}
