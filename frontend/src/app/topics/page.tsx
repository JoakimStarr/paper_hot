'use client';

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { Compass, Sparkles, Loader2, Table2, ShieldCheck, RefreshCw, Database, Square, CheckCircle2, ChevronRight, ChevronDown, Brain, Save, Trash2, FolderKanban, BookMarked, FileText } from 'lucide-react';
import Layout from '@/components/Layout';
import { useLanguage } from '@/contexts/LanguageContext';
import { topicsApi, streamValidateTopic, generateTopicProposal } from '@/lib/api';
import { reportPageContext } from '@/lib/assistantBus';
import { downloadTextFile } from '@/lib/utils';
import type { GapAnalysisResponse, ResearchGap, RetrievedPaper, TopicProject, ValidatorStatus } from '@/types/paper';
import ProducerLab from './ProducerLab';

// 重组件按需加载：react-markdown 栈独立懒 chunk（与 trends 页同模式）
const MarkdownRenderer = dynamic(() => import('@/components/MarkdownRenderer'), {
  ssr: false,
  loading: () => (
    <div className="h-20 flex items-center justify-center text-gray-400 text-sm animate-pulse">加载中...</div>
  ),
});

// 后台任务轮询间隔（对齐 trends 页模式，前密后疏）
const POLL_INTERVALS = [3000, 5000, 8000, 13000, 13000];

type TabKey = 'gaps' | 'validator' | 'library' | 'producer';

export default function TopicsPage() {
  const { t } = useLanguage();
  const [tab, setTab] = useState<TabKey>('gaps');
  // 工作台深链：?review={id} 直接打开指定综述
  const [initialReviewId, setInitialReviewId] = useState<number | null>(null);

  // ---- 研究空白 ----
  const [gaps, setGaps] = useState<ResearchGap[]>([]);
  const [gapsLoading, setGapsLoading] = useState(true);
  const [gapAnalysis, setGapAnalysis] = useState<GapAnalysisResponse | null>(null);
  const [gapAnalyzing, setGapAnalyzing] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollCountRef = useRef(0);

  // ---- 选题验证 ----
  const [validatorStatus, setValidatorStatus] = useState<ValidatorStatus | null>(null);
  const [backfilling, setBackfilling] = useState(false);
  const [topicInput, setTopicInput] = useState('');
  const [sourceGapOfInput, setSourceGapOfInput] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  const [reportContent, setReportContent] = useState('');
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportReasoning, setReportReasoning] = useState('');
  const [reasoningOpen, setReasoningOpen] = useState(true);
  const [retrievedPapers, setRetrievedPapers] = useState<RetrievedPaper[]>([]);
  const [retrievedMode, setRetrievedMode] = useState('');
  // 召回论文 → [n] 引用映射：让验证报告里的 [n] 可点击跳转论文详情
  const reportCitations = useMemo(() => {
    const map: Record<number, { id: string; title?: string }> = {};
    for (const p of retrievedPapers) {
      if (p.n !== undefined) map[p.n] = { id: String(p.id), title: p.title };
    }
    return map;
  }, [retrievedPapers]);
  const [savingProject, setSavingProject] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const backfillTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---- P2-12b 竞争地图 / P2-12a 立项书 ----
  const [competition, setCompetition] = useState<{
    top_authors: Array<{ name: string; count: number }>;
    journal_distribution: Array<{ journal: string; count: number }>;
    recent_1y_count: number;
  } | null>(null);
  const [proposal, setProposal] = useState<string | null>(null);
  const [proposalBusy, setProposalBusy] = useState(false);
  const proposalGeneratedForRef = useRef('');

  // ---- 选题库（决策层） ----
  const [projects, setProjects] = useState<TopicProject[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);

  // ---- 数据加载 ----
  const loadGaps = useCallback(async () => {
    setGapsLoading(true);
    try {
      const res = await topicsApi.getResearchGaps(15);
      setGaps(res.gaps || []);
    } catch {
      setGaps([]);
    } finally {
      setGapsLoading(false);
    }
  }, []);

  const loadGapAnalysis = useCallback(async () => {
    try {
      const res = await topicsApi.getGapAnalysis();
      setGapAnalysis(res);
      if (res.is_running) {
        setGapAnalyzing(true);
      }
    } catch {
      /* 忽略：无报告时静默 */
    }
  }, []);

  const loadValidatorStatus = useCallback(async () => {
    try {
      const res = await topicsApi.getValidatorStatus();
      setValidatorStatus(res);
      return res;
    } catch {
      /* 忽略 */
      return undefined;
    }
  }, []);

  const loadProjects = useCallback(async () => {
    try {
      setProjectsLoading(true);
      const res = await topicsApi.listTopicProjects();
      setProjects(res || []);
    } catch {
      setProjects([]);
    } finally {
      setProjectsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGaps();
    loadGapAnalysis();
    loadValidatorStatus();
    loadProjects();
    // 卸载清理：向量补齐轮询定时器
    return () => {
      if (backfillTimerRef.current) clearTimeout(backfillTimerRef.current);
    };
  }, [loadGaps, loadGapAnalysis, loadValidatorStatus, loadProjects]);

  // 跨页预填：网络图「转选题」等入口把题目写入 localStorage，这里读取并切到验证 tab
  useEffect(() => {
    try {
      const prefill = localStorage.getItem('pp_topic_prefill');
      if (prefill) {
        setTopicInput(prefill);
        setTab('validator');
        localStorage.removeItem('pp_topic_prefill');
      }
    } catch { /* ignore */ }
    const tabParam = new URLSearchParams(window.location.search).get('tab');
    if (tabParam === 'validator' || tabParam === 'library' || tabParam === 'producer') {
      setTab(tabParam);
    }
    // 工作台深链：?review={id} 直接打开指定综述
    const reviewParam = new URLSearchParams(window.location.search).get('review');
    if (reviewParam && /^\d+$/.test(reviewParam)) {
      setInitialReviewId(Number(reviewParam));
    }
  }, []);

  // 后台任务轮询：running 期间按递增间隔查状态，完成后刷新。
  // ref 式自调度（对齐 trends 页 startPolling）：网络抖动等异常不断链，连续失败超限才放弃
  useEffect(() => {
    if (!gapAnalyzing) return;

    const stopPolling = () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };

    if (pollTimerRef.current) return;
    pollCountRef.current = 0;
    let failCount = 0;

    const tick = async () => {
      try {
        const res = await topicsApi.getGapAnalysis();
        failCount = 0;
        setGapAnalysis(res);
        if (!res.is_running) {
          setGapAnalyzing(false);
          pollCountRef.current = 0;
          pollTimerRef.current = null;
          return;
        }
      } catch {
        // 网络抖动继续轮询；连续失败超过 10 次则放弃，避免轮询悬挂
        failCount += 1;
        if (failCount > 10) {
          setGapAnalyzing(false);
          pollCountRef.current = 0;
          pollTimerRef.current = null;
          return;
        }
      }
      pollCountRef.current = Math.min(pollCountRef.current + 1, POLL_INTERVALS.length - 1);
      pollTimerRef.current = setTimeout(tick, POLL_INTERVALS[pollCountRef.current]);
    };

    pollTimerRef.current = setTimeout(tick, POLL_INTERVALS[0]);
    return stopPolling;
  }, [gapAnalyzing]);

  // ---- 交互 ----
  const startGapAnalysis = async () => {
    if (gapAnalyzing) return;
    setGapAnalyzing(true);
    pollCountRef.current = 0;
    try {
      await topicsApi.startGapAnalysis(undefined, 15);
    } catch (e: any) {
      setGapAnalyzing(false);
      setGapAnalysis(prev => prev ? { ...prev, error_message: e.message } : prev);
    }
  };

  const handleBackfill = async () => {
    if (backfilling) return;
    setBackfilling(true);
    try {
      // 触发一次性全量增量补建（后端内部循环直到补齐），期间轮询刷新进度
      await topicsApi.backfillEmbeddings(500);
      // 后台构建需要时间：轮询刷新，直至达到全量；attempts 上限 60 次（约 3 分钟）防无限轮询
      let attempts = 0;
      if (backfillTimerRef.current) clearTimeout(backfillTimerRef.current);
      const poll = async () => {
        attempts += 1;
        const s = await loadValidatorStatus();
        const done = s && s.embedded_papers && s.total_papers
          ? s.embedded_papers >= s.total_papers
          : true;
        if (done || attempts > 60) {
          setBackfilling(false);
        } else {
          backfillTimerRef.current = setTimeout(poll, 3000);
        }
      };
      backfillTimerRef.current = setTimeout(poll, 3000);
    } catch {
      setBackfilling(false);
    }
  };

  const handleValidate = async () => {
    const topic = topicInput.trim();
    if (!topic || validating) return;
    setValidating(true);
    setReportContent('');
    setReportError(null);
    setReportReasoning('');
    setReasoningOpen(true);
    setRetrievedPapers([]);
    setRetrievedMode('');
    setSaveMsg(null);
    setCompetition(null);
    setProposal(null);
    proposalGeneratedForRef.current = '';
    const controller = new AbortController();
    abortRef.current = controller;
    await streamValidateTopic(
      topic,
      undefined,
      {
        onContent: (text) => setReportContent(text),
        onReasoning: (text) => setReportReasoning(text),
        onMeta: (data) => {
          // 首条"论文召回"元消息：recall 可见化 + 竞争地图（P2-12b）
          if (data && typeof data === 'object' && 'papers' in data) {
            const meta = data as any;
            setRetrievedPapers(Array.isArray(meta.papers) ? meta.papers as RetrievedPaper[] : []);
            setRetrievedMode(typeof meta.mode === 'string' ? meta.mode : '');
            if (meta.stats?.competition) {
              setCompetition(meta.stats.competition);
            }
          }
        },
        onDone: () => setValidating(false),
        onError: (msg) => {
          setReportError(msg);
          setValidating(false);
        },
      },
      controller.signal,
    );
  };

  // P2-12a：验证完成后自动生成选题立项书（每个题目只自动生成一次，可手动重试）
  useEffect(() => {
    const topic = topicInput.trim();
    if (
      validating || proposalBusy || !topic || !reportContent || reportError ||
      proposalGeneratedForRef.current === topic
    ) return;
    proposalGeneratedForRef.current = topic;
    setProposalBusy(true);
    generateTopicProposal(topic, reportContent.slice(0, 1500))
      .then((res) => setProposal(res.proposal))
      .catch(() => { proposalGeneratedForRef.current = ''; })
      .finally(() => setProposalBusy(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [validating, reportContent, reportError]);

  const handleAbort = () => {
    abortRef.current?.abort();
    setValidating(false);
  };

  /** f1 联动：把一条研究空白组合带入验证器并切换到验证 tab。 */
  const runGapInValidator = (g: ResearchGap) => {
    if (validating) return;
    setTopicInput(`交叉研究：${g.source} 与 ${g.target} 的结合`);
    setSourceGapOfInput(`${g.source}×${g.target}`);
    setTab('validator');
  };

  /** f3 保存：把当前验证结果存入选题库（携带来源空白词对 + 报告）。 */
  const saveCurrentReport = async () => {
    const title = topicInput.trim();
    if (!title || savingProject || !reportContent) return;
    setSavingProject(true);
    setSaveMsg(null);
    try {
      await topicsApi.createTopicProject({
        title,
        source_gap: sourceGapOfInput || undefined,
        validation_report: reportContent,
      });
      setSaveMsg('ok');
      loadProjects();
    } catch (e: any) {
      setSaveMsg('err');
    } finally {
      setSavingProject(false);
    }
  };

  /** f3 决策流转：更新选题状态/评分。 */
  const updateProject = async (p: TopicProject, patch: Partial<Pick<TopicProject, 'status' | 'novelty' | 'crowding' | 'feasibility'>>) => {
    try {
      const updated = await topicsApi.updateTopicProject(p.id, patch);
      setProjects((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
    } catch {
      /* 忽略 */
    }
  };

  const deleteProject = async (id: number) => {
    try {
      await topicsApi.deleteTopicProject(id);
      setProjects((prev) => prev.filter((x) => x.id !== id));
    } catch {
      /* 忽略 */
    }
  };

  const embedReady = (validatorStatus?.embedded_papers ?? 0) > 0;

  return (
    <Layout>
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center gap-2 mb-2">
          <Compass className="w-6 h-6 text-primary-600" />
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">
            {t('tp.title')}
          </h1>
        </div>
        <p className="text-sm sm:text-base text-gray-600 dark:text-gray-400">
          {t('tp.subtitle')}
        </p>
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => { setTab('gaps'); reportPageContext({ tab: 'gaps' }); }}
          className={`flex items-center gap-1.5 px-3.5 py-2 text-sm rounded-md transition-colors ${
            tab === 'gaps'
              ? 'bg-primary-600 text-white'
              : 'bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
          }`}
        >
          <Table2 className="w-4 h-4" />
          {t('tp.tabGaps')}
        </button>
        <button
          onClick={() => { setTab('validator'); reportPageContext({ tab: 'validator' }); }}
          className={`flex items-center gap-1.5 px-3.5 py-2 text-sm rounded-md transition-colors ${
            tab === 'validator'
              ? 'bg-primary-600 text-white'
              : 'bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
          }`}
        >
          <ShieldCheck className="w-4 h-4" />
          {t('tp.tabValidator')}
        </button>
        <button
          onClick={() => { setTab('library'); reportPageContext({ tab: 'library' }); }}
          className={`flex items-center gap-1.5 px-3.5 py-2 text-sm rounded-md transition-colors ${
            tab === 'library'
              ? 'bg-primary-600 text-white'
              : 'bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
          }`}
        >
          <FolderKanban className="w-4 h-4" />
          选题库
        </button>
        <button
          onClick={() => { setTab('producer'); reportPageContext({ tab: 'producer' }); }}
          className={`flex items-center gap-1.5 px-3.5 py-2 text-sm rounded-md transition-colors ${
            tab === 'producer'
              ? 'bg-primary-600 text-white'
              : 'bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
          }`}
        >
          <BookMarked className="w-4 h-4" />
          产出工作台
        </button>
      </div>

      {/* ==================== Tab 1：研究空白 ==================== */}
      {tab === 'gaps' && (
        <div className="space-y-6">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
              <div>
                <h2 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white">
                  {t('tp.gapsTitle')}
                </h2>
                <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mt-1 max-w-2xl">
                  {t('tp.gapsDesc')}
                </p>
              </div>
              <button
                onClick={startGapAnalysis}
                disabled={gapAnalyzing || gaps.length === 0}
                className="flex items-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-white text-sm rounded-md transition-colors shrink-0"
              >
                {gapAnalyzing ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4" />
                )}
                {gapAnalysis?.status === 'success' ? t('tp.gapReanalyze') : t('tp.gapAnalyze')}
              </button>
            </div>

            {gapsLoading ? (
              <div className="flex justify-center items-center py-10">
                <Loader2 className="w-6 h-6 animate-spin text-primary-600" />
              </div>
            ) : gaps.length === 0 ? (
              <div className="text-center py-10 text-gray-400 text-sm">{t('tp.gapEmpty')}</div>
            ) : (
              <div className="overflow-x-auto -mx-4 sm:mx-0">
                <table className="w-full text-sm min-w-[560px]">
                  <thead>
                    <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                      <th className="py-2.5 px-3 font-medium">#</th>
                      <th className="py-2.5 px-3 font-medium">{t('tp.keyword')} A</th>
                      <th className="py-2.5 px-3 font-medium">{t('tp.keyword')} B</th>
                      <th className="py-2.5 px-3 font-medium text-right">{t('tp.freq')} A</th>
                      <th className="py-2.5 px-3 font-medium text-right">{t('tp.freq')} B</th>
                      <th className="py-2.5 px-3 font-medium text-right">{t('tp.cooc')}</th>
                      <th className="py-2.5 px-3 font-medium text-right">{t('tp.gapScore')}</th>
                      <th className="py-2.5 px-3 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gaps.map((g, i) => (
                      <tr key={`${g.source}-${g.target}`} className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                        <td className="py-2.5 px-3 text-gray-400">{i + 1}</td>
                        <td className="py-2.5 px-3">
                          <span className="inline-flex px-2 py-0.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs font-medium">
                            {g.source}
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="inline-flex px-2 py-0.5 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded text-xs font-medium">
                            {g.target}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-right text-gray-600 dark:text-gray-300">{g.source_count}</td>
                        <td className="py-2.5 px-3 text-right text-gray-600 dark:text-gray-300">{g.target_count}</td>
                        <td className="py-2.5 px-3 text-right text-gray-600 dark:text-gray-300">{g.cooccurrence}</td>
                        <td className="py-2.5 px-3 text-right">
                          <span className="font-semibold text-purple-600 dark:text-purple-400">{g.gap_score.toFixed(3)}</span>
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          <button
                            onClick={() => runGapInValidator(g)}
                            disabled={validating}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-primary-600 dark:text-primary-400 border border-primary-200 dark:border-primary-700/50 rounded-md hover:bg-primary-50 dark:hover:bg-primary-900/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                            title="用这个空白组合生成交叉选题并验证"
                          >
                            验证
                            <ChevronRight className="w-3 h-3" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* AI 空白假设卡片 */}
          {(gapAnalyzing || gapAnalysis?.status === 'success' || gapAnalysis?.status === 'failed') && (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-6">
              <div className="flex items-center gap-2 mb-4">
                <Sparkles className="w-5 h-5 text-purple-600" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  {t('tp.gapAnalysisTitle')}
                </h2>
                {gapAnalysis?.model && (
                  <span className="text-xs text-gray-400 font-mono">{gapAnalysis.model}</span>
                )}
              </div>

              {gapAnalyzing && (
                <div className="flex flex-col items-center justify-center py-10 gap-3">
                  <Loader2 className="w-7 h-7 animate-spin text-purple-500" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">{t('tp.gapAnalyzing')}</p>
                </div>
              )}

              {!gapAnalyzing && gapAnalysis?.status === 'success' && gapAnalysis.raw_analysis && (
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <MarkdownRenderer content={gapAnalysis.raw_analysis} />
                </div>
              )}

              {!gapAnalyzing && gapAnalysis?.status === 'failed' && (
                <div className="text-sm text-red-500 py-4">
                  {gapAnalysis.error_message || 'Analysis failed'}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ==================== Tab 2：选题验证 ==================== */}
      {tab === 'validator' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
            <div>
              <h2 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white">
                {t('tp.valTitle')}
              </h2>
              <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mt-1 max-w-2xl">
                {t('tp.valDesc')}
              </p>
            </div>
            {/* 向量索引状态 */}
            <div className="flex items-center gap-2 shrink-0">
              {validatorStatus && (
                <span
                  className={`flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-full ${
                    embedReady
                      ? 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                      : 'bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400'
                  }`}
                  title={`${validatorStatus.embedded_papers}/${validatorStatus.total_papers}`}
                >
                  <Database className="w-3.5 h-3.5" />
                  {embedReady ? t('tp.valEmbedReady') : t('tp.valEmbedFallback')}
                </span>
              )}
              {validatorStatus && validatorStatus.total_papers > 0 && (
                <button
                  onClick={handleBackfill}
                  disabled={backfilling}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded-md transition-colors disabled:opacity-50"
                  title={`${validatorStatus.embedded_papers}/${validatorStatus.total_papers}`}
                >
                  {backfilling ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="w-3.5 h-3.5" />
                  )}
                  {backfilling
                    ? `${t('tp.valBackfilling')} ${validatorStatus.embedded_papers}/${validatorStatus.total_papers}`
                    : t('tp.valRebuild')}
                </button>
              )}
            </div>
          </div>

          {/* 输入区 */}
          <div className="flex flex-col sm:flex-row gap-2 mb-6">
            <input
              type="text"
              value={topicInput}
              onChange={(e) => setTopicInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleValidate();
              }}
              placeholder={t('tp.valPlaceholder')}
              maxLength={200}
              className="flex-1 px-3.5 py-2.5 border border-gray-300 dark:border-gray-600 dark:bg-gray-700 rounded-md text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            />
            {validating ? (
              <button
                onClick={handleAbort}
                className="flex items-center justify-center gap-1.5 px-4 py-2.5 bg-red-500 hover:bg-red-600 text-white text-sm rounded-md transition-colors shrink-0"
              >
                <Square className="w-4 h-4" />
                {t('tp.valAbort')}
              </button>
            ) : (
              <button
                onClick={handleValidate}
                disabled={!topicInput.trim()}
                className="flex items-center justify-center gap-1.5 px-4 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-white text-sm rounded-md transition-colors shrink-0"
              >
                <ShieldCheck className="w-4 h-4" />
                {t('tp.valButton')}
              </button>
            )}
          </div>

          {/* 结果区：召回论文可见化（f2）+ 报告 + 存入选题库（f3） */}
          {(validating || reportContent || reportError) && (
            <div>
              {/* 召回论文卡片：把 LLM 判断依据摊开给用户 */}
              {retrievedPapers.length > 0 && (
                <div className="mb-5">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                      召回依据（{retrievedPapers.length} 篇·{retrievedMode === 'embedding' ? '语义检索' : 'TF-IDF'}）
                    </h3>
                  </div>
                  <ul className="space-y-1.5">
                    {retrievedPapers.slice(0, 12).map((p) => (
                      <li key={p.id}>
                        <a
                          href={`/paper/${p.id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center justify-between gap-3 px-3 py-2 bg-gray-50 dark:bg-gray-700/40 border border-gray-200 dark:border-gray-600 rounded-md hover:border-primary-400 transition-colors"
                        >
                          <span className="flex-1 min-w-0 text-xs sm:text-sm text-gray-700 dark:text-gray-300 truncate">
                            {p.n !== undefined && <span className="text-gray-400 mr-1.5 font-mono">[{p.n}]</span>}
                            {p.title}
                          </span>
                          <span className="flex items-center gap-2 shrink-0">
                            <span className="text-[11px] text-gray-400 font-mono">
                              {(p.similarity * 100).toFixed(1)}%
                            </span>
                            <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
                          </span>
                        </a>
                      </li>
                    ))}
                  </ul>
                  {retrievedPapers.length === 0 && (
                    <p className="text-xs text-gray-400 mt-2">
                      （未召回近似论文：该题目的表述在库内近乎无匹配）
                    </p>
                  )}
                </div>
              )}

              {/* 竞争地图（P2-12b）：谁在做、发到哪、近一年多少篇 */}
              {competition && (competition.top_authors.length > 0 || competition.journal_distribution.length > 0) && (
                <div className="mb-5 bg-indigo-50/60 dark:bg-indigo-900/15 border border-indigo-100 dark:border-indigo-800/40 rounded-lg p-4">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2.5">
                    竞争地图
                    <span className="ml-2 text-xs font-normal text-gray-400">
                      近一年 {competition.recent_1y_count} 篇
                    </span>
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-gray-500 mb-1.5">谁在做（活跃作者）</p>
                      <div className="flex flex-wrap gap-1.5">
                        {competition.top_authors.map((a) => (
                          <a
                            key={a.name}
                            href={`/author/${encodeURIComponent(a.name)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs px-2 py-1 bg-white dark:bg-gray-700/50 border border-indigo-200 dark:border-indigo-800 rounded-full hover:border-indigo-400 transition-colors"
                          >
                            {a.name}
                            <span className="text-gray-400 ml-1">{a.count}</span>
                          </a>
                        ))}
                        {competition.top_authors.length === 0 && <span className="text-xs text-gray-400">无</span>}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 mb-1.5">发到哪里（期刊分布）</p>
                      <div className="flex flex-wrap gap-1.5">
                        {competition.journal_distribution.map((j) => (
                          <span key={j.journal} className="text-xs px-2 py-1 bg-white dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-full">
                            {j.journal}
                            <span className="text-gray-400 ml-1">{j.count}</span>
                          </span>
                        ))}
                        {competition.journal_distribution.length === 0 && <span className="text-xs text-gray-400">无</span>}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* 思考过程（深度思考）可见化：模型返回 reasoning_content 时展示，可折叠 */}
              {reportReasoning && (
                <div className="mb-4">
                  <button
                    onClick={() => setReasoningOpen(!reasoningOpen)}
                    className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 transition-colors"
                  >
                    <Brain className="w-3.5 h-3.5" />
                    思考过程
                    <span className="px-1.5 py-px text-[10px] leading-4 bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-300 rounded">
                      深度思考
                    </span>
                    <ChevronDown className={`w-3.5 h-3.5 transition-transform ${reasoningOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {reasoningOpen && (
                    <div className="mt-2 max-h-72 overflow-y-auto rounded-md bg-gray-50 dark:bg-gray-700/40 border border-gray-200 dark:border-gray-600 p-3 text-xs text-gray-500 dark:text-gray-400 whitespace-pre-wrap leading-relaxed">
                      {reportReasoning}
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center gap-2 mb-3">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                  {t('tp.valResult')}
                </h3>
                {validating && <Loader2 className="w-4 h-4 animate-spin text-primary-500" />}
              </div>
              {reportError ? (
                <div className="text-sm text-red-500 py-4">{reportError}</div>
              ) : (
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <MarkdownRenderer content={reportContent || '...'} citations={reportCitations} />
                </div>
              )}

              {/* 存入选题库 */}
              {reportContent && !validating && (
                <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                  {saveMsg === 'ok' ? (
                    <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
                      <CheckCircle2 className="w-4 h-4" />
                      已存入选题库
                      <button
                        onClick={() => setTab('library')}
                        className="ml-2 text-primary-600 dark:text-primary-400 underline underline-offset-2 hover:text-primary-700"
                      >
                        查看
                      </button>
                    </div>
                  ) : saveMsg === 'err' ? (
                    <div className="text-sm text-red-500">保存失败，请重试</div>
                  ) : (
                    <button
                      onClick={saveCurrentReport}
                      disabled={savingProject}
                      className="flex items-center gap-1.5 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 text-white text-sm rounded-md transition-colors"
                    >
                      {savingProject ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Save className="w-4 h-4" />
                      )}
                      存入选题库
                    </button>
                  )}
                </div>
              )}

              {/* 选题立项书（P2-12a）：验证完成后自动生成 */}
              {(proposalBusy || proposal) && reportContent && !validating && (
                <div className="mt-5 border-t border-gray-200 dark:border-gray-700 pt-5">
                  <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
                      <FileText className="w-4 h-4 text-green-600" />
                      选题立项书（自动生成）
                    </h3>
                    {proposal && (
                      <div className="flex gap-2">
                        <button
                          onClick={() => downloadTextFile(`立项书_${topicInput.trim().slice(0, 20)}_${Date.now()}.md`, proposal, 'text/markdown;charset=utf-8')}
                          className="text-xs px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 hover:border-primary-400 text-gray-700 dark:text-gray-300"
                        >
                          下载 Markdown
                        </button>
                        <button
                          onClick={() => setProposal(null)}
                          disabled={proposalBusy}
                          className="text-xs px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-500 disabled:opacity-50"
                        >
                          重新生成
                        </button>
                      </div>
                    )}
                  </div>
                  {proposalBusy ? (
                    <div className="flex items-center gap-2 text-sm text-gray-400 py-3">
                      <Loader2 className="w-4 h-4 animate-spin" /> 正在生成立项书（数据来源建议 / 方法论 / 研究设计）…
                    </div>
                  ) : proposal ? (
                    <div className="prose prose-sm dark:prose-invert max-w-none">
                      <MarkdownRenderer content={proposal} />
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ==================== Tab 3：选题库 ==================== */}
      {tab === 'library' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
            <div>
              <h2 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white">选题库</h2>
              <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mt-1 max-w-2xl">
                已验证/订阅/放弃的选题项目管理，支持评分、状态流转与沉淀回看。
              </p>
            </div>
            <button
              onClick={loadProjects}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded-md transition-colors shrink-0"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              刷新
            </button>
          </div>

          {projectsLoading ? (
            <div className="flex justify-center items-center py-10">
              <Loader2 className="w-6 h-6 animate-spin text-primary-600" />
            </div>
          ) : projects.length === 0 ? (
            <div className="text-center py-10 text-gray-400 text-sm">
              暂无选题。先在「研究空白」中发现机会，或在「选题验证」中验证并保存一个选题。
            </div>
          ) : (
            <div className="overflow-x-auto -mx-4 sm:mx-0">
              <table className="w-full text-sm min-w-[760px]">
                <thead>
                  <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                    <th className="py-2.5 px-3 font-medium">选题</th>
                    <th className="py-2.5 px-3 font-medium">来源</th>
                    <th className="py-2.5 px-3 font-medium text-center">新颖度</th>
                    <th className="py-2.5 px-3 font-medium text-center">拥挤度</th>
                    <th className="py-2.5 px-3 font-medium text-center">可行性</th>
                    <th className="py-2.5 px-3 font-medium text-center">状态</th>
                    <th className="py-2.5 px-3 font-medium">更新</th>
                    <th className="py-2.5 px-3 font-medium text-center">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((p) => (
                    <tr key={p.id} className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                      <td className="py-2.5 px-3 max-w-[260px]">
                        <div className="font-medium text-gray-800 dark:text-gray-200 truncate" title={p.title}>
                          {p.title}
                        </div>
                        {p.source_gap && (
                          <span className="inline-flex mt-1 px-1.5 py-0.5 bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-300 rounded text-[11px]">
                            空白:{p.source_gap}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-xs text-gray-400">
                        {p.created_at ? new Date(p.created_at).toLocaleDateString() : '-'}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <input
                          type="number"
                          min={1}
                          max={10}
                          value={p.novelty ?? ''}
                          placeholder="-"
                          onChange={(e) => {
                            const v = Number(e.target.value);
                            if (v >= 1 && v <= 10) updateProject(p, { novelty: v });
                          }}
                          className="w-14 px-1.5 py-1 text-center text-sm border border-gray-300 dark:border-gray-600 dark:bg-gray-700 rounded"
                        />
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <select
                          value={p.crowding || ''}
                          onChange={(e) => updateProject(p, { crowding: e.target.value || undefined })}
                          className="px-1.5 py-1 text-sm border border-gray-300 dark:border-gray-600 dark:bg-gray-700 rounded"
                        >
                          <option value="">-</option>
                          <option value="低">低</option>
                          <option value="中">中</option>
                          <option value="高">高</option>
                        </select>
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <input
                          type="number"
                          min={1}
                          max={10}
                          value={p.feasibility ?? ''}
                          placeholder="-"
                          onChange={(e) => {
                            const v = Number(e.target.value);
                            if (v >= 1 && v <= 10) updateProject(p, { feasibility: v });
                          }}
                          className="w-14 px-1.5 py-1 text-center text-sm border border-gray-300 dark:border-gray-600 dark:bg-gray-700 rounded"
                        />
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <span className={`inline-flex px-2 py-0.5 text-xs rounded-full ${
                          p.status === 'validated'
                            ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                            : p.status === 'subscribed'
                            ? 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                            : p.status === 'abandoned'
                            ? 'bg-gray-100 dark:bg-gray-700 text-gray-500'
                            : 'bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400'
                        }`}>
                          {p.status === 'validated' ? '已验证' : p.status === 'subscribed' ? '订阅中' : p.status === 'abandoned' ? '已放弃' : '待验证'}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-xs text-gray-400">
                        {p.updated_at ? new Date(p.updated_at).toLocaleString() : '-'}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <div className="flex items-center justify-center gap-1.5">
                          <button
                            onClick={() => updateProject(p, { status: p.status === 'validated' ? 'subscribed' : 'validated' })}
                            className="px-2 py-1 text-xs text-primary-600 dark:text-primary-400 border border-gray-200 dark:border-gray-600 rounded hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                          >
                            {p.status === 'subscribed' ? '取消订阅' : '订阅'}
                          </button>
                          <button
                            onClick={() => deleteProject(p.id)}
                            className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                            title="删除"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ==================== Tab 4：产出工作台（综述生成 + 期刊适配） ==================== */}
      {tab === 'producer' && <ProducerLab initialReviewId={initialReviewId} />}
    </Layout>
  );
}
