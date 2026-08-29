'use client';

import dynamic from 'next/dynamic';
import React, { useState, useEffect, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import Filters from '@/components/Filters';
import Pagination from '@/components/Pagination';
import SkeletonCard from '@/components/SkeletonCard';
const MarkdownRenderer = dynamic(() => import('@/components/MarkdownRenderer'), {
  ssr: false,
});
import { Loader2, X, Sparkles, FileDown, Clock, ArrowUp } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { getBookmarks } from '@/lib/cache';
import { usePapersPage } from '@/lib/usePapersPage';
import { usePageTitle } from '@/lib/usePageTitle';
import { usePreferences } from '@/lib/usePreferences';
import { usePins } from '@/lib/usePins';
import { useToast } from '@/components/Toast';
import { papersApi, personalApi, producerApi, dashboardApi, TodayBrief } from '@/lib/api';
import type { PaperCard as PaperCardType } from '@/types/paper';
import { downloadTextFile } from '@/lib/utils';

/** 首页「今日速览条」：今日/近一个月新发表/关注子领域统计；点击仅刷新数据。 */
function TodayBriefBar() {
  const { t } = useLanguage();
  const [brief, setBrief] = useState<TodayBrief | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setBrief(await dashboardApi.getTodayBrief());
    } catch {
      /* 静默失败：速览条不阻塞首页论文流 */
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!brief) return null;

  return (
    <button
      onClick={load}
      title={t('home.clickRefresh')}
      className="w-full mb-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-left bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 hover:border-primary-400 dark:hover:border-primary-500 px-4 py-3 transition-colors"
    >
      <Clock className="w-4 h-4 text-primary-600 dark:text-primary-400 shrink-0" />
      <span className="text-sm text-gray-500 dark:text-gray-400">
        {t('home.todayCount').replace('{n}', String(brief.today_count))}
      </span>
      <span className="text-gray-300 dark:text-gray-600">·</span>
      <span className="text-sm text-gray-500 dark:text-gray-400">
        {t('home.monthCount').replace('{n}', String(brief.month_count))}
      </span>
      {brief.watch_subfield_count !== null && brief.watch_subfield_count !== undefined && (
        <>
          <span className="text-gray-300 dark:text-gray-600">·</span>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {t('home.watchCount').replace('{n}', String(brief.watch_subfield_count))}
          </span>
        </>
      )}
      {refreshing && <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400 ml-auto" />}
    </button>
  );
}

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
  usePageTitle(t('nav.home'));
  const { toast } = useToast();
  const searchParams = useSearchParams();

  const [minScore, setMinScore] = useState<number | null>(null);
  const [selectedSubfield, setSelectedSubfield] = useState<string[]>([]);
  const [selectedCnkiSubject, setSelectedCnkiSubject] = useState<string[]>([]);
  const [selectedJournal, setSelectedJournal] = useState<string[]>([]);
  const [showBookmarksOnly, setShowBookmarksOnly] = useState(false);
  const [sortBy, setSortBy] = useState('date');
  const [sortOrder, setSortOrder] = useState('desc');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchField, setSearchField] = useState('');

  // 「不感兴趣」屏蔽版本号：新增/删除屏蔽项时列表需重取（后端已在列表层过滤）
  const { version: prefVersion } = usePreferences();
  // 置顶变化后重取列表（后端把置顶论文恒排最前）
  const { version: pinVersion } = usePins();

  // —— 批量操作（P1-8 / P2-11）：多选 -> AI 综述摘要 / 引用导出 ——
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchBusy, setBatchBusy] = useState<'review' | 'cite' | null>(null);
  const [batchSummary, setBatchSummary] = useState<string | null>(null);
  // #7 异步化：批量分析轮询句柄
  const batchPollRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const batchPollCount = React.useRef(0);

  useEffect(() => {
    const journal = searchParams.get('journal');
    if (journal) setSelectedJournal([journal]);
  }, [searchParams]);

  // #7：卸载时清理批量分析轮询定时器
  useEffect(() => {
    return () => {
      if (batchPollRef.current) clearTimeout(batchPollRef.current);
    };
  }, []);

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
    search: searchQuery.trim() || undefined,
    search_field: searchField || undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
  }), [minScore, selectedSubfield, selectedCnkiSubject, selectedJournal, sortBy, sortOrder, searchQuery, searchField]);

  // 数据流收敛在 lib/usePapersPage.ts（与搜索页共用），首页额外启用 3 页预取
  const {
    papers, loading, total, totalPages,
    page, pageSize, handlePageChange, handlePageSizeChange, readIds,
  } = usePapersPage({
    buildParams,
    deps: [sortBy, sortOrder, minScore, selectedSubfield, selectedCnkiSubject, selectedJournal, searchQuery, searchField, prefVersion, pinVersion],
    cacheBust: prefVersion,
    prefetch: 3,
  });

  const selectedPapers = papers.filter((p) => selectedIds.has(p.id));

  // 收藏过滤：切换到「仅看收藏」时加载全量论文并筛选，避免只看到当前页的收藏
  const [allPapersForBookmarks, setAllPapersForBookmarks] = useState<PaperCardType[]>([]);
  const [bookmarksLoading, setBookmarksLoading] = useState(false);

  useEffect(() => {
    if (!showBookmarksOnly) { setAllPapersForBookmarks([]); return; }
    let cancelled = false;
    setBookmarksLoading(true);
    // 直连服务端收藏列表（此前按页扫描全库，大库且收藏靠后时会「筛选不出来」）
    personalApi.getFavorites()
      .then((res) => { if (!cancelled) setAllPapersForBookmarks(res.papers || []); })
      .catch(() => { /* 忽略，保持空列表 */ })
      .finally(() => { if (!cancelled) setBookmarksLoading(false); });
    return () => { cancelled = true; };
  }, [showBookmarksOnly, prefVersion]);

  const displayedPapers = showBookmarksOnly
    ? allPapersForBookmarks
    : papers;

  // 命中数提示：仅在真实影响服务端命中的筛选/搜索激活时显示（不含纯客户端「仅看收藏」）
  const hasActiveFilter = minScore !== null || selectedSubfield.length > 0 || selectedCnkiSubject.length > 0 || selectedJournal.length > 0 || searchQuery.trim() !== '';

  const handleBatchReview = async () => {
    if (selectedIds.size === 0 || batchBusy) return;
    setBatchBusy('review');
    setBatchSummary(null);
    batchPollCount.current = 0;
    try {
      // #7 异步化：先提交拿 batch_id，后台生成，前端轮询（前密后疏）拿结果
      const { batch_id } = await papersApi.startBatchAnalyze(Array.from(selectedIds).slice(0, 10));
      const pollNext = () => {
        if (batchPollRef.current) clearTimeout(batchPollRef.current);
        const interval = [1500, 2000, 3000, 5000][Math.min(batchPollCount.current, 3)];
        batchPollRef.current = setTimeout(async () => {
          batchPollCount.current += 1;
          try {
            const res = await papersApi.getBatchAnalyze(batch_id);
            if (res.status === 'success') {
              setBatchSummary(res.content ?? '');
              setBatchBusy(null);
            } else if (res.status === 'failed') {
              toast(`批量分析失败：${res.error_message || '未知错误'}`, 'error');
              setBatchBusy(null);
            } else if (batchPollCount.current > 60) {
              toast('批量分析等待超时，请重试', 'error');
              setBatchBusy(null);
            } else {
              pollNext();
            }
          } catch {
            pollNext(); // 网络抖动继续轮询
          }
        }, interval);
      };
      pollNext();
    } catch (e) {
      toast(`批量分析失败：${e instanceof Error ? e.message : '未知错误'}`, 'error');
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
      toast(`导出失败：${e instanceof Error ? e.message : '未知错误'}`, 'error');
    } finally {
      setBatchBusy(null);
    }
  };



  return (
    <Layout>
      <div className="mb-4">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
          {t('home.title')}
        </h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mb-4">
          {t('home.subtitle')}
        </p>
      </div>

      {/* 今日速览条（点击刷新） */}
      <TodayBriefBar />

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
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        searchField={searchField}
        onSearchFieldChange={setSearchField}
        selectionMode={selectionMode}
        onToggleSelection={() => {
          setSelectionMode((s) => !s);
          setSelectedIds(new Set());
        }}
      />

      {/* 批量操作的「进入多选」开关下沉到筛选栏（低调虚线按钮），避免常驻工具条抢视线 */}

      {hasActiveFilter && (
        <div className="mb-3 text-sm text-gray-500 dark:text-gray-400">
          匹配 <strong className="font-semibold text-gray-700 dark:text-gray-200">{total.toLocaleString()}</strong> 篇
        </div>
      )}

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
                read={readIds.has(paper.id)}
                selectable={selectionMode}
                selected={selectedIds.has(paper.id)}
                onToggleSelect={toggleSelect}
              />
            ))}
          </div>

          {papers.length === 0 && !showBookmarksOnly && (
            <div className="text-center py-12">
              <p className="text-gray-600 dark:text-gray-400">{t('home.noPapers')}</p>
            </div>
          )}

          {showBookmarksOnly && !bookmarksLoading && displayedPapers.length === 0 && (
            <div className="text-center py-12">
              <p className="text-gray-600 dark:text-gray-400">{t('home.noPapers')}</p>
            </div>
          )}

          {showBookmarksOnly && bookmarksLoading && (
            <div className="flex justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-primary-600" />
            </div>
          )}

          {total > 0 && !showBookmarksOnly && (
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              totalItems={total}
              pageSize={pageSize}
              onPageChange={handlePageChange}
              onPageSizeChange={handlePageSizeChange}
            />
          )}

          {showBookmarksOnly && displayedPapers.length > 0 && (
            <div className="text-center text-sm text-gray-500 dark:text-gray-400 py-4">
              共 {displayedPapers.length} 篇收藏
            </div>
          )}
        </>
      )}

      {/* 情景式批量操作浮动条：仅进入多选模式后出现，避免默认浏览视图被抢视线 */}
      {selectionMode && (
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 sm:gap-3 rounded-full bg-gray-900 dark:bg-gray-800 text-white px-3 sm:px-4 py-2 shadow-xl border border-white/10 max-w-[calc(100vw-2rem)] overflow-x-auto">
          <span className="text-xs whitespace-nowrap shrink-0">已选 {selectedIds.size} 篇（最多 10）</span>
          <button
            onClick={handleBatchReview}
            disabled={selectedIds.size === 0 || !!batchBusy}
            className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-purple-600 text-white text-xs sm:text-sm disabled:opacity-40 hover:bg-purple-700 transition-colors whitespace-nowrap shrink-0"
          >
            {batchBusy === 'review' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            AI 领域综述摘要
          </button>
          <button
            onClick={() => exportCitations('bibtex')}
            disabled={selectedIds.size === 0 || !!batchBusy}
            className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-white/10 text-white text-xs sm:text-sm disabled:opacity-40 hover:bg-white/20 transition-colors whitespace-nowrap shrink-0"
          >
            {batchBusy === 'cite' ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileDown className="w-4 h-4" />}
            导出 BibTeX
          </button>
          <button
            onClick={() => exportCitations('gbt7714')}
            disabled={selectedIds.size === 0 || !!batchBusy}
            className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-white/10 text-white text-xs sm:text-sm disabled:opacity-40 hover:bg-white/20 transition-colors whitespace-nowrap shrink-0"
          >
            <FileDown className="w-4 h-4" />
            导出 GB/T 7714
          </button>
          <button
            onClick={() => {
              setSelectionMode(false);
              setSelectedIds(new Set());
            }}
            className="px-3 py-1.5 rounded-full text-white/80 text-xs sm:text-sm hover:text-white hover:bg-white/10 transition-colors whitespace-nowrap shrink-0"
          >
            取消
          </button>
        </div>
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
      {/* 回到顶部 */}
      <BackToTop />
    </Layout>
  );
}

/** 回到顶部浮动按钮：滚动超过 400px 后显示。 */
function BackToTop() {
  const { t } = useLanguage();
  const [show, setShow] = useState(false);

  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 400);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  if (!show) return null;

  return (
    <button
      onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
      className="fixed bottom-20 right-5 z-40 p-2.5 rounded-full bg-white dark:bg-gray-800 shadow-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:text-primary-600 hover:border-primary-400 transition-colors"
      title={t('home.backToTop')}
    >
      <ArrowUp className="w-5 h-5" />
    </button>
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
