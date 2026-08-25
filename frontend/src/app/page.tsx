'use client';

import React, { useState, useEffect, useCallback, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import Filters from '@/components/Filters';
import Pagination from '@/components/Pagination';
import SkeletonCard from '@/components/SkeletonCard';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import { Loader2, Search, X, Sparkles, FileDown } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { getBookmarks } from '@/lib/cache';
import { usePapersPage } from '@/lib/usePapersPage';
import { papersApi, producerApi } from '@/lib/api';
import type { PaperCard as PaperCardType } from '@/types/paper';
import { downloadTextFile } from '@/lib/utils';

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

  // —— 批量操作（P1-8 / P2-11）：多选 -> AI 综述摘要 / 引用导出 ——
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchBusy, setBatchBusy] = useState<'review' | 'cite' | null>(null);
  const [batchSummary, setBatchSummary] = useState<string | null>(null);

  useEffect(() => {
    const journal = searchParams.get('journal');
    if (journal) setSelectedJournal([journal]);
  }, [searchParams]);

  const toggleSelect = useCallback((paperId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(paperId)) next.delete(paperId);
      else next.add(paperId);
      return next;
    });
  }, []);

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

  const selectedPapers = papers.filter((p) => selectedIds.has(p.id));

  const handleBatchReview = async () => {
    if (selectedIds.size === 0 || batchBusy) return;
    setBatchBusy('review');
    try {
      const res = await papersApi.batchAnalyzePapers(Array.from(selectedIds).slice(0, 10));
      setBatchSummary(res.summary);
    } catch (e) {
      alert(`批量分析失败：${e instanceof Error ? e.message : '未知错误'}`);
    } finally {
      setBatchBusy(null);
    }
  };

  const exportCitations = async (format: 'gbt7714' | 'bibtex') => {
    if (selectedIds.size === 0 || batchBusy) return;
    setBatchBusy('cite');
    try {
      const snapshots = selectedPapers.map(toCitationSnapshot);
      const res = await producerApi.exportCitations(snapshots, format);
      downloadTextFile(
        `citations_${format}_${Date.now()}.${format === 'bibtex' ? 'bib' : 'txt'}`,
        res.citations.join('\n\n'),
      );
    } catch (e) {
      alert(`导出失败：${e instanceof Error ? e.message : '未知错误'}`);
    } finally {
      setBatchBusy(null);
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

      {/* 批量操作工具条（P1-8 / P2-11） */}
      <div className="my-3 flex flex-wrap items-center gap-2 text-sm">
        <button
          onClick={() => {
            setSelectionMode((s) => !s);
            setSelectedIds(new Set());
          }}
          className={`px-3 py-1.5 rounded-lg border transition-colors ${
            selectionMode
              ? 'bg-primary-600 text-white border-primary-600'
              : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-primary-400'
          }`}
        >
          {selectionMode ? '退出多选' : '批量操作'}
        </button>
        {selectionMode && (
          <>
            <span className="text-xs text-gray-500">已选 {selectedIds.size} 篇（最多 10 篇）</span>
            <button
              onClick={handleBatchReview}
              disabled={selectedIds.size === 0 || !!batchBusy}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-purple-600 text-white disabled:opacity-50 hover:bg-purple-700 transition-colors"
            >
              {batchBusy === 'review' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              AI 领域综述摘要
            </button>
            <button
              onClick={() => exportCitations('bibtex')}
              disabled={selectedIds.size === 0 || !!batchBusy}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 disabled:opacity-50 hover:border-primary-400 transition-colors"
            >
              {batchBusy === 'cite' ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileDown className="w-4 h-4" />}
              导出 BibTeX
            </button>
            <button
              onClick={() => exportCitations('gbt7714')}
              disabled={selectedIds.size === 0 || !!batchBusy}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 disabled:opacity-50 hover:border-primary-400 transition-colors"
            >
              <FileDown className="w-4 h-4" />
              导出 GB/T 7714
            </button>
          </>
        )}
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
            {displayedPapers.map((paper) => (
              <PaperCard
                key={paper.id}
                paper={paper}
                selectable={selectionMode}
                selected={selectedIds.has(paper.id)}
                onToggleSelect={toggleSelect}
              />
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

      {/* 批量综述结果弹窗 */}
      {batchSummary && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => setBatchSummary(null)}>
          <div
            className="bg-white dark:bg-gray-800 rounded-xl max-w-3xl w-full max-h-[85vh] overflow-y-auto p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">AI 领域综述摘要</h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => downloadTextFile(`领域综述_${Date.now()}.md`, batchSummary, 'text/markdown;charset=utf-8')}
                  className="text-sm px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 hover:border-primary-400 text-gray-700 dark:text-gray-300"
                >
                  下载 Markdown
                </button>
                <button onClick={() => setBatchSummary(null)} className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              </div>
            </div>
            <MarkdownRenderer content={batchSummary} />
          </div>
        </div>
      )}
    </Layout>
  );
}

/** 论文卡片 -> 引用导出快照（producer/citations 需要的最小字段集）。 */
function toCitationSnapshot(p: PaperCardType): Record<string, unknown> {
  return {
    id: p.id,
    title: p.title,
    authors: p.authors || [],
    journal_name: p.journal_name,
    journal_issue: p.journal_issue,
    published_at: p.published_at,
  };
}
