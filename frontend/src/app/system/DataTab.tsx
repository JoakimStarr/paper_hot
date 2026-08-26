'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Database, Trash2, Loader2, PieChart, CalendarDays, Brain, RefreshCw, GitCompareArrows, DownloadCloud, TrendingUp, Layers,
} from 'lucide-react';
import { SystemStats, MaintenanceResult, DataHealth, NetworkNode } from '@/types/paper';
import { papersApi, topicsApi } from '@/lib/api';
import { useLanguage } from '@/contexts/LanguageContext';

interface DataTabProps {
  stats: SystemStats | null;
  cleaning: boolean;
  cleanupMessage: string;
  cleanupResult: MaintenanceResult | null;
  onCleanup: () => void;
}

/** 简单横向条形图（用于来源/年度分布） */
function DistributionBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-20 shrink-0 truncate text-gray-600 dark:text-gray-300" title={label}>{label}</span>
      <div className="flex-1 h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
        <div className="h-full bg-primary-500 rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 shrink-0 text-right text-gray-500 dark:text-gray-400">{value}</span>
    </div>
  );
}

function StatCard({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
      <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 mb-1">
        {icon}
        {label}
      </div>
      <div className="text-xl font-bold text-gray-900 dark:text-white">{value}</div>
    </div>
  );
}

export default function DataTab({
  stats,
  cleaning,
  cleanupMessage,
  cleanupResult,
  onCleanup,
}: DataTabProps) {
  const { t } = useLanguage();

  // —— 数据健康中心独立状态 ——
  const [dataHealth, setDataHealth] = useState<DataHealth | null>(null);
  const [koKeywords, setKoKeywords] = useState<NetworkNode[]>([]);
  // 动作态
  const [backfilling, setBackfilling] = useState(false);
  const [refreshingTrend, setRefreshingTrend] = useState(false);
  const [recomputing, setRecomputing] = useState(false);
  const [actionMessage, setActionMessage] = useState<string>('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const loadHealth = useCallback(async () => {
    try {
      const res = await papersApi.getDataHealth();
      setDataHealth(res);
    } catch {
      // 后端不可用时保留旧值
    }
  }, []);

  const loadKo = useCallback(async () => {
    try {
      const res = await papersApi.getKeywordNetwork(12);
      const nodes = (res.nodes || [])
        .slice()
        .sort((a, b) => ((b.count ?? b.papers ?? 0)) - ((a.count ?? a.papers ?? 0)))
        .slice(0, 10);
      setKoKeywords(nodes);
    } catch {
      setKoKeywords([]);
    }
  }, []);

  useEffect(() => {
    loadHealth();
    loadKo();
    return stopPoll;
  }, [loadHealth, loadKo, stopPoll]);

  // 补齐向量：触发后轮询直到缺失清零
  const handleBackfill = async () => {
    setActionMessage('');
    setBackfilling(true);
    try {
      await topicsApi.backfillEmbeddings(100);
      setActionMessage(t('sys.bfStarted'));
      stopPoll();
      pollRef.current = setInterval(async () => {
        const res = await papersApi.getDataHealth().catch(() => null);
        if (res) {
          setDataHealth(res);
          if (res.embedding.missing <= 0) {
            stopPoll();
            setBackfilling(false);
            setActionMessage(t('sys.bfDone'));
          }
        }
      }, 3000);
    } catch {
      setBackfilling(false);
      setActionMessage(t('sys.bfFailed'));
    }
  };

  // 刷新趋势
  const handleRefreshTrend = async () => {
    setActionMessage('');
    setRefreshingTrend(true);
    try {
      await papersApi.triggerTrendUpdate();
      setActionMessage(t('sys.trendRefreshed'));
      setTimeout(() => { loadHealth(); setRefreshingTrend(false); }, 2500);
    } catch {
      setRefreshingTrend(false);
      setActionMessage(t('sys.trendFailed'));
    }
  };

  // 重算相似度：触发后轮询 running 直到结束
  const handleRecompute = async () => {
    setActionMessage('');
    setRecomputing(true);
    try {
      await papersApi.triggerRecomputeSimilarities();
      setActionMessage(t('sys.simStarted'));
      stopPoll();
      pollRef.current = setInterval(async () => {
        const st = await papersApi.getSimilaritiesStatus().catch(() => null);
        if (st && !st.running) {
          stopPoll();
          setRecomputing(false);
          loadHealth();
          setActionMessage(t('sys.simDone'));
        }
      }, 4000);
    } catch {
      setRecomputing(false);
      setActionMessage(t('sys.simFailed'));
    }
  };

  useEffect(() => stopPoll, [stopPoll]);

  const fmt = (s: string | null) => {
    if (!s) return '-';
    const safe = (/[Zz]$/.test(s) || /[+\-]\d{2}:\d{2}$/.test(s)) ? s : s + 'Z';
    const d = new Date(safe);
    return Number.isNaN(d.getTime()) ? '-' : d.toLocaleString();
  };

  const embedding = dataHealth?.embedding;
  const embedRate = embedding && embedding.total > 0 ? Math.round((embedding.embedded / embedding.total) * 100) : 0;
  const trend = dataHealth?.trend;
  const sim = dataHealth?.similarity;

  // 来源/年度 top 数据
  const sources = (stats?.source_counts ? Object.entries(stats.source_counts).sort((a, b) => b[1] - a[1]).slice(0, 6) : []);
  const years = (stats?.year_counts ? Object.entries(stats.year_counts).sort((a, b) => b[0].localeCompare(a[0])).slice(0, 6) : []);
  const journals = (stats?.top_journals ? Object.entries(stats.top_journals).slice(0, 8) : []);
  const ai = stats?.ai_usage;
  const sourceMax = Math.max(1, ...(sources.map(([, c]) => c)));
  const yearMax = Math.max(1, ...(years.map(([, c]) => c)));

  return (
    <div className="space-y-6">
      {/* 基础指标 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center gap-3 mb-4">
          <Database className="w-6 h-6 text-primary-600" />
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('sys.dbStats')}</h2>
        </div>
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.totalPapers')}</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.total_papers}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.journals')}</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.journal_count}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.keywords')}</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.keyword_count}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.dbSize')}</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">
                {stats.db_size_mb ? `${stats.db_size_mb.toFixed(1)} MB` : '-'}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 数据分布 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center gap-3 mb-4">
          <PieChart className="w-6 h-6 text-primary-600" />
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('sys.dataDist')}</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <h4 className="text-sm font-medium text-gray-600 dark:text-gray-300 mb-2">{t('sys.bySource')}</h4>
            {sources.length ? (
              <div className="space-y-2">{sources.map(([k, c]) => <DistributionBar key={k} label={k} value={c} max={sourceMax} />)}</div>
            ) : <p className="text-sm text-gray-400">{t('sys.noData')}</p>}
          </div>
          <div>
            <h4 className="text-sm font-medium text-gray-600 dark:text-gray-300 mb-2">{t('sys.byYear')}</h4>
            {years.length ? (
              <div className="space-y-2">{years.map(([k, c]) => <DistributionBar key={k} label={k} value={c} max={yearMax} />)}</div>
            ) : <p className="text-sm text-gray-400">{t('sys.noData')}</p>}
          </div>
          <div>
            <h4 className="text-sm font-medium text-gray-600 dark:text-gray-300 mb-2">{t('sys.topJournals')}</h4>
            {journals.length ? (
              <ol className="space-y-1.5 text-xs">
                {journals.map(([k, c], i) => (
                  <li key={k} className="flex items-center gap-2">
                    <span className={`w-5 h-5 shrink-0 flex items-center justify-center rounded-full text-[10px] font-medium ${i < 3 ? 'bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'}`}>{i + 1}</span>
                    <span className="flex-1 truncate text-gray-700 dark:text-gray-300" title={k}>{k}</span>
                    <span className="text-gray-500 dark:text-gray-400">{c}</span>
                  </li>
                ))}
              </ol>
            ) : <p className="text-sm text-gray-400">{t('sys.noData')}</p>}
          </div>
        </div>
        {/* 入库/爬取状态 */}
        <div className="mt-5 pt-5 border-t border-gray-100 dark:border-gray-700 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="flex items-center gap-2 text-sm">
            <CalendarDays className="w-4 h-4 text-gray-400" />
            <span className="text-gray-500 dark:text-gray-400">{t('sys.latestPaper')}</span>
            <span className="ml-auto text-gray-800 dark:text-gray-200 truncate">{fmt(stats?.latest_paper_at ?? null)}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <RefreshCw className="w-4 h-4 text-gray-400" />
            <span className="text-gray-500 dark:text-gray-400">{t('sys.latestCrawl')}</span>
            <span className="ml-auto text-gray-800 dark:text-gray-200 truncate">{fmt(stats?.latest_crawl_at ?? null)}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <ActivityDot running={!!stats?.scheduler_running} />
            <span className="text-gray-500 dark:text-gray-400">{t('sys.schedulerStatus')}</span>
            <span className={`ml-auto font-medium ${stats?.scheduler_running ? 'text-green-600' : 'text-gray-500 dark:text-gray-400'}`}>
              {stats?.scheduler_running ? t('sys.running') : t('sys.stopped')}
            </span>
          </div>
        </div>
      </div>

      {/* AI 用量 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center gap-3 mb-4">
          <Brain className="w-6 h-6 text-primary-600" />
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('sys.aiUsage')}</h2>
        </div>
        {ai ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard label={t('sys.aiAnalyses')} value={ai.total_analyses} icon={<PulseDot />} />
              <StatCard label={t('sys.aiTokens')} value={ai.total_tokens?.toLocaleString?.() ?? ai.total_tokens ?? 0} icon={<Brain className="w-3 h-3" />} />
              <StatCard label={t('sys.aiTime')} value={ai.total_processing_ms ? `${(ai.total_processing_ms / 1000).toFixed(1)}s` : 0} icon={<TimerIcon />} />
              <StatCard label={t('sys.aiPapers')} value={ai.total_papers_analyzed} icon={<Layers className="w-3 h-3" />} />
            </div>
            {ai.by_model && ai.by_model.length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm font-medium text-gray-600 dark:text-gray-300 mb-2">{t('sys.byModel')}</h4>
                <div className="space-y-1.5">
                  {ai.by_model.map((m) => (
                    <div key={m.model} className="flex items-center gap-2 text-xs">
                      <span className="w-40 truncate text-gray-700 dark:text-gray-300" title={m.model}>{m.model}</span>
                      <div className="flex-1 h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                        <div className="h-full bg-purple-500" style={{ width: `${ai.total_analyses ? Math.round((m.count / ai.total_analyses) * 100) : 0}%` }} />
                      </div>
                      <span className="w-24 shrink-0 text-right text-gray-500 dark:text-gray-400">{m.count} / {m.tokens?.toLocaleString?.() ?? m.tokens}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : <p className="text-sm text-gray-400">{t('sys.noData')}</p>}
      </div>

      {/* 向量覆盖 + 补齐 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <DownloadCloud className="w-6 h-6 text-blue-600" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('sys.vectorCoverage')}</h2>
          </div>
          <button
            onClick={handleBackfill}
            disabled={backfilling || !embedding || embedding.missing <= 0}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {backfilling ? <Loader2 className="w-4 h-4 animate-spin" /> : <DownloadCloud className="w-4 h-4" />}
            {backfilling ? t('sys.backfilling') : t('sys.backfillNow')}
          </button>
        </div>
        {embedding ? (
          <>
            <div className="flex items-end justify-between mb-1">
              <span className="text-sm text-gray-600 dark:text-gray-300">
                {t('sys.embedded')}: <b className="text-gray-900 dark:text-white">{embedding.embedded}</b>
                <span className="text-gray-400"> / total {embedding.total}</span>
              </span>
              <span className="text-sm font-semibold text-gray-900 dark:text-white">{embedRate}%</span>
            </div>
            <div className="h-3 w-full bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden mb-2">
              <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${embedRate}%` }} />
            </div>
            <p className={`text-xs ${embedding.missing > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-green-600 dark:text-green-400'}`}>
              {embedding.missing > 0
                ? `${t('sys.missingVectors')}: ${embedding.missing}`
                : t('sys.allEmbedded')}
            </p>
          </>
        ) : <p className="text-sm text-gray-400">{t('sys.noData')}</p>}
      </div>

      {/* 趋势分析情况 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <TrendingUp className="w-6 h-6 text-emerald-600" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('sys.trendStatus')}</h2>
          </div>
          <button
            onClick={handleRefreshTrend}
            disabled={refreshingTrend}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors"
          >
            {refreshingTrend ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            {t('sys.refreshTrend')}
          </button>
        </div>
        {trend ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label={t('sys.trendTopics')} value={trend.topics} icon={<TrendingUp className="w-3 h-3" />} />
            <StatCard label={t('sys.trendRecords')} value={trend.records} icon={<Layers className="w-3 h-3" />} />
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.latestWeek')}</div>
              <div className="text-sm font-semibold text-gray-900 dark:text-white">{fmt(trend.latest_week_start)}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.updatedAt')}</div>
              <div className="text-sm font-semibold text-gray-900 dark:text-white">{fmt(trend.latest_updated_at)}</div>
            </div>
          </div>
        ) : <p className="text-sm text-gray-400">{t('sys.noData')}</p>}
      </div>

      {/* 相关性 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <GitCompareArrows className="w-6 h-6 text-purple-600" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('sys.similarityStatus')}</h2>
          </div>
          <button
            onClick={handleRecompute}
            disabled={recomputing || sim?.running}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors"
          >
            {recomputing || sim?.running ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitCompareArrows className="w-4 h-4" />}
            {recomputing || sim?.running ? t('sys.recomputing') : t('sys.recomputeSim')}
          </button>
        </div>
        {sim ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard label={t('sys.simPairs')} value={sim.pairs} icon={<GitCompareArrows className="w-3 h-3" />} />
              <StatCard label={t('sys.simPapers')} value={sim.covered_papers} icon={<Layers className="w-3 h-3" />} />
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.simLatest')}</div>
                <div className="text-sm font-semibold text-gray-900 dark:text-white">{fmt(sim.latest_computed_at)}</div>
              </div>
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.simState')}</div>
                <div className={`text-sm font-semibold ${sim.running ? 'text-blue-600' : 'text-green-600'}`}>
                  {sim.running ? t('sys.simRunning') : t('sys.simIdle')}
                </div>
              </div>
            </div>
            <div className="mt-5 pt-4 border-t border-gray-100 dark:border-gray-700">
              <h4 className="text-sm font-medium text-gray-600 dark:text-gray-300 mb-2">{t('sys.cooccurring')}</h4>
              {koKeywords.length ? (
                <div className="flex flex-wrap gap-2">
                  {koKeywords.map((n) => (
                    <span key={n.id} className="inline-flex items-center gap-1.5 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 text-xs px-2.5 py-1 rounded-full">
                      {n.name}
                      <span className="text-purple-400">{n.count ?? n.papers ?? 0}</span>
                    </span>
                  ))}
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-400">{t('sys.noData')}</span>
                  <a href="/network" className="text-xs text-purple-600 hover:underline">{t('sys.gotoNetwork')}</a>
                </div>
              )}
            </div>
          </>
        ) : <p className="text-sm text-gray-400">{t('sys.noData')}</p>}
      </div>

      {/* 动作反馈 */}
      {actionMessage && (
        <div className="p-3 rounded-lg text-sm text-gray-700 dark:text-gray-200 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
          {actionMessage}
        </div>
      )}

      {/* 清理维护（保留原样） */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Trash2 className="w-6 h-6 text-red-500" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('sys.cleanupTitle')}</h2>
          </div>
          <button
            onClick={onCleanup}
            disabled={cleaning}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
          >
            {cleaning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
            {t('sys.cleanupTitle')}
          </button>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          {t('sys.cleanupDesc')}
        </p>
        {cleanupMessage && (
          <div className={`p-3 rounded-lg text-sm ${cleanupMessage.includes('失败') ? 'bg-red-50 dark:bg-red-900/30 text-red-600' : 'bg-green-50 dark:bg-green-900/30 text-green-600'}`}>
            {cleanupMessage}
          </div>
        )}
        {cleanupResult && (
          <div className="mt-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">{t('sys.cleanupResult')}</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {([
                ['sys.deletedPapers', cleanupResult.deleted_papers],
                ['sys.deletedFeatures', cleanupResult.deleted_features],
                ['sys.deletedScores', cleanupResult.deleted_scores],
                ['sys.deletedReports', cleanupResult.deleted_reports],
              ] as const).map(([k, v]) => (
                <div key={k}>
                  <div className="text-xs text-gray-500 dark:text-gray-400">{t(k)}</div>
                  <div className="text-lg font-bold text-gray-900 dark:text-white">{v}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// —— 若干小图标/状态组件（避免引入更多图标）——
function ActivityDot({ running }: { running: boolean }) {
  return (
    <span className={`w-2.5 h-2.5 rounded-full ${running ? 'bg-green-500 animate-pulse' : 'bg-gray-300'}`} />
  );
}
function PulseDot() {
  return <span className="w-2 h-2 rounded-full bg-purple-400" />;
}
function TimerIcon() {
  return (
    <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="13" r="8" /><path d="M12 9v4l2.5 2.5M9 2h6" /></svg>
  );
}