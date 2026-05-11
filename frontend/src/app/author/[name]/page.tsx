'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import Pagination from '@/components/Pagination';
import SkeletonCard from '@/components/SkeletonCard';
import { papersApi } from '@/lib/api';
import { ArrowLeft, User, Users } from 'lucide-react';
import { PaperCard as PaperCardType } from '@/types/paper';

export default function AuthorPage() {
  const params = useParams();
  const authorName = decodeURIComponent((params.name as string) || '');

  const [papers, setPapers] = useState<PaperCardType[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [coAuthors, setCoAuthors] = useState<{ name: string; count: number }[]>([]);
  const [authorStats, setAuthorStats] = useState<{
    total_papers: number;
    first_author_count: number;
    recent_year: string | null;
    top_journal: string | null;
    top_keywords: string[];
    top_subfield: string | null;
  } | null>(null);

  const fetchPapers = useCallback(async (p: number) => {
    if (!authorName) return;
    setLoading(true);
    try {
      const response = await papersApi.getAuthorPapers(authorName, p, pageSize);
      setPapers(response.papers);
      setTotal(response.total);
      setTotalPages(Math.ceil(response.total / pageSize));

      const allPapers = await papersApi.getAuthorPapers(authorName, 1, 200);
      computeStats(allPapers.papers);
    } catch (error) {
      console.error('Error fetching author papers:', error);
    } finally {
      setLoading(false);
    }
  }, [authorName, pageSize]);

  useEffect(() => {
    if (authorName) {
      setPage(1);
      fetchPapers(1);
    }
  }, [authorName]);

  useEffect(() => {
    if (authorName && page > 1) {
      fetchPapers(page);
    }
  }, [page]);

  const computeStats = (allPapers: PaperCardType[]) => {
    const coAuthorMap = new Map<string, number>();
    let firstAuthorCount = 0;
    const yearCounts: Record<string, number> = {};
    const journalCounts: Record<string, number> = {};
    const keywordCounts: Record<string, number> = {};
    const subfieldCounts: Record<string, number> = {};

    for (const paper of allPapers) {
      if (paper.authors && paper.authors[0]?.trim() === authorName) {
        firstAuthorCount++;
      }
      for (const a of paper.authors || []) {
        const aClean = a.trim();
        if (aClean && aClean !== authorName) {
          coAuthorMap.set(aClean, (coAuthorMap.get(aClean) || 0) + 1);
        }
      }
      if (paper.published_at) {
        const year = paper.published_at.substring(0, 4);
        yearCounts[year] = (yearCounts[year] || 0) + 1;
      }
      if (paper.journal_name) {
        journalCounts[paper.journal_name] = (journalCounts[paper.journal_name] || 0) + 1;
      }
      for (const kw of paper.keywords_cn || []) {
        keywordCounts[kw] = (keywordCounts[kw] || 0) + 1;
      }
      if (paper.economics_subfield) {
        subfieldCounts[paper.economics_subfield] = (subfieldCounts[paper.economics_subfield] || 0) + 1;
      }
    }

    const sortedCoAuthors = Array.from(coAuthorMap.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([name, count]) => ({ name, count }));

    const sortedYears = Object.entries(yearCounts).sort((a, b) => b[0].localeCompare(a[0]));
    const sortedJournals = Object.entries(journalCounts).sort((a, b) => b[1] - a[1]);
    const sortedKeywords = Object.entries(keywordCounts).sort((a, b) => b[1] - a[1]).slice(0, 5);
    const sortedSubfields = Object.entries(subfieldCounts).sort((a, b) => b[1] - a[1]);

    setCoAuthors(sortedCoAuthors);
    setAuthorStats({
      total_papers: allPapers.length,
      first_author_count: firstAuthorCount,
      recent_year: sortedYears[0]?.[0] || null,
      top_journal: sortedJournals[0]?.[0] || null,
      top_keywords: sortedKeywords.map(([k]) => k),
      top_subfield: sortedSubfields[0]?.[0] || null,
    });
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

  if (!authorName) {
    return (
      <Layout>
        <div className="text-center py-12">
          <p className="text-gray-500 dark:text-gray-400">无效的作者名称</p>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="mb-6">
        <Link href="/" className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-primary-600 transition-colors mb-6">
          <ArrowLeft className="w-5 h-5" />
          <span>返回首页</span>
        </Link>

        <div className="flex items-start gap-4 mb-2">
          <div className="w-14 h-14 rounded-full bg-primary-100 flex items-center justify-center shrink-0">
            <User className="w-7 h-7 text-primary-600" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">{authorName}</h1>
            <p className="text-gray-500 dark:text-gray-400 mt-1">
              共发表 {total} 篇论文
              {authorStats?.first_author_count && authorStats.first_author_count > 0
                ? `，其中 ${authorStats.first_author_count} 篇为第一作者`
                : ''}
            </p>
          </div>
        </div>

        {authorStats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-6">
            {authorStats.recent_year && (
              <div className="bg-blue-50 dark:bg-blue-900/30 rounded-lg p-3">
                <div className="text-xs text-blue-500 mb-0.5">最新发表</div>
                <div className="font-semibold text-blue-700">{authorStats.recent_year} 年</div>
              </div>
            )}
            {authorStats.top_journal && (
              <div className="bg-green-50 dark:bg-green-900/30 rounded-lg p-3">
                <div className="text-xs text-green-500 mb-0.5">高频期刊</div>
                <div className="font-semibold text-green-700 text-sm truncate" title={authorStats.top_journal}>
                  {authorStats.top_journal}
                </div>
              </div>
            )}
            {authorStats.top_subfield && (
              <div className="bg-purple-50 dark:bg-purple-900/30 rounded-lg p-3">
                <div className="text-xs text-purple-500 mb-0.5">研究方向</div>
                <div className="font-semibold text-purple-700 text-sm">{authorStats.top_subfield}</div>
              </div>
            )}
            {authorStats.top_keywords.length > 0 && (
              <div className="bg-orange-50 dark:bg-orange-900/30 rounded-lg p-3">
                <div className="text-xs text-orange-500 mb-0.5">研究关键词</div>
                <div className="font-semibold text-orange-700 text-sm truncate" title={authorStats.top_keywords.join(', ')}>
                  {authorStats.top_keywords.slice(0, 3).join(', ')}
                </div>
              </div>
            )}
          </div>
        )}

        {coAuthors.length > 0 && (
          <div className="mt-6 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex items-center gap-2 mb-3">
              <Users className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              <h2 className="font-semibold text-gray-900 dark:text-white">合作学者</h2>
            </div>
            <div className="flex flex-wrap gap-2">
              {coAuthors.map((ca) => (
                <Link
                  key={ca.name}
                  href={`/author/${encodeURIComponent(ca.name)}`}
                  className="inline-flex items-center gap-1 px-3 py-1.5 bg-gray-50 dark:bg-gray-700/50 hover:bg-primary-50 dark:bg-primary-900/30 text-gray-700 dark:text-gray-300 hover:text-primary-700 rounded-full text-sm border border-gray-200 dark:border-gray-700 hover:border-primary-200 transition-colors"
                >
                  {ca.name}
                  <span className="text-xs text-gray-400">({ca.count})</span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mb-4">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">论文列表</h2>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
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
              <p className="text-gray-500 dark:text-gray-400">未找到该作者的论文</p>
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
      )}
    </Layout>
  );
}