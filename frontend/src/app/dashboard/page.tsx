'use client';

import React, { useState, useEffect, useCallback, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import PreferencesPanel from '@/components/PreferencesPanel';
import SkeletonCard from '@/components/SkeletonCard';
import { useToast } from '@/components/Toast';
import { dashboardApi, DashboardData, personalApi } from '@/lib/api';
import { reportPageContext } from '@/lib/assistantBus';
import { usePreferences } from '@/lib/usePreferences';
import { refreshPreferences } from '@/lib/cache';
import { useLanguage } from '@/contexts/LanguageContext';
import { PaperCard as PaperCardType, TrendingTopic } from '@/types/paper';
import {
  BookOpen, Newspaper, Layers, Sparkles, TrendingUp, TrendingDown,
  Minus, Bookmark, FileSearch, Target, Loader2, Plus, History, SlidersHorizontal, BookMarked,
  RefreshCw, ChevronDown, Check, Clock, X,
} from 'lucide-react';

const trendIcon = (trend: string) =>
  trend === 'rising' ? (
    <TrendingUp className="w-3.5 h-3.5 text-red-500" />
  ) : trend === 'declining' ? (
    <TrendingDown className="w-3.5 h-3.5 text-blue-500" />
  ) : (
    <Minus className="w-3.5 h-3.5 text-gray-400" />
  );

/** api.ts 的 DashboardData 内联类型不含 series / watch_subfield_count，这里扩展以兼容后端返回 */
type BriefingTopic = TrendingTopic & { series?: Array<{ year: string; count: number }> };
type MineData = DashboardData['mine'] & { watch_subfield_count?: number | null };

/** 迷你逐年柱状图（领域快讯 sparkline）：高度按 count/max 归一化，title 显示「年份: 篇数」 */
function TopicSparkline({ series }: { series?: Array<{ year: string; count: number }> }) {
  if (!series || series.length === 0) return null;
  const max = Math.max(...series.map((s) => s.count), 1);
  return (
    <div className="hidden sm:flex items-end gap-0.5 h-5 shrink-0">
      {series.map((s) => (
        <div
          key={s.year}
          title={`${s.year}: ${s.count}`}
          className="w-1.5 rounded-sm bg-primary-400/70 dark:bg-primary-500/70"
          style={{ height: `${Math.round((s.count / max) * 18) + 2}px` }}
        />
      ))}
    </div>
  );
}

type DashboardTab = 'workbench' | 'briefing' | 'stack' | 'prefs';
const VALID_TABS: DashboardTab[] = ['workbench', 'briefing', 'stack', 'prefs'];

// 各页签需要的 /dashboard 子集：prefs 页签纯客户端，不需要聚合接口
const TAB_SECTIONS: Record<DashboardTab, Array<'today_read' | 'briefing' | 'mine'>> = {
  workbench: ['today_read', 'mine'],
  briefing: ['briefing'],
  stack: ['mine'],
  prefs: [],
};

export default function DashboardPage() {
  return (
    <Suspense fallback={
      <Layout>
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      </Layout>
    }>
      <DashboardInner />
    </Suspense>
  );
}

function DashboardInner() {
  const { t } = useLanguage();
  const searchParams = useSearchParams();

  // 模块页签；支持 ?tab= 深链（承接原 #follow / #mine 锚点跳转）
  const tabParam = searchParams.get('tab');
  const [activeTab, setActiveTab] = useState<DashboardTab>(
    tabParam && (VALID_TABS as string[]).includes(tabParam) ? (tabParam as DashboardTab) : 'workbench'
  );

  // 按页签拆分取数：各页签只拉所需子集（后端 /dashboard?sections=...），
  // 首屏只算「研究工作台」，领域快讯/研究栈切到时再取并缓存，屏蔽项变化只刷新当前页签。
  const [dataByTab, setDataByTab] = useState<Partial<Record<DashboardTab, Partial<DashboardData>>>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 「不感兴趣」屏蔽版本号：新增/删除屏蔽项后重取工作台，保证「今日值得读」即时生效
  const { version: prefVersion } = usePreferences();

  // 关注变更版本号：SuggestionBar/FollowSubfields/FollowKeywords 变化时触发子组件重取
  const [followVersion, setFollowVersion] = useState(0);

  const [seed, setSeed] = useState(0);
  const seedRef = React.useRef(0);

  const loadTab = useCallback(async (tab: DashboardTab, s: number, silent = false) => {
    const sections = TAB_SECTIONS[tab];
    if (sections.length === 0) return;
    if (!silent) setLoading(true);
    setError(null);
    try {
      const fresh = await dashboardApi.getDashboard(s, sections);
      setDataByTab((prev) => ({ ...prev, [tab]: { ...(prev[tab] || {}), ...fresh } }));
    } catch (e) {
      if (!silent) setError(e instanceof Error ? e.message : t('dash.loadFailed'));
    } finally {
      if (!silent) setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadTab('workbench', 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 页签切换：页内跳转 / 深链共用；未取过的页签按需取数
  const switchTab = useCallback((tab: DashboardTab) => {
    setActiveTab(tab);
    reportPageContext({ tab });
    if (TAB_SECTIONS[tab].length > 0 && !dataByTab[tab]) {
      loadTab(tab, seedRef.current);
    }
  }, [dataByTab, loadTab]);

  // 页内 Link 跳转到 /dashboard?tab=xxx 时同步激活页签
  useEffect(() => {
    const p = searchParams.get('tab');
    if (p && (VALID_TABS as string[]).includes(p)) {
      switchTab(p as DashboardTab);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // 屏蔽项变化 / 「换一批」「看过了」时只静默重取当前页签子集；reloading 仅在顶部小节显示轻量加载指示
  const [reloading, setReloading] = useState(false);
  const skipFirstPref = React.useRef(true);
  useEffect(() => {
    if (skipFirstPref.current) {
      skipFirstPref.current = false;
      return;
    }
    let cancelled = false;
    setReloading(true);
    (async () => {
      try {
        const fresh = await dashboardApi.getDashboard(seed, TAB_SECTIONS[activeTab]);
        if (!cancelled) {
          setDataByTab((prev) => ({ ...prev, [activeTab]: { ...(prev[activeTab] || {}), ...fresh } }));
        }
      } catch {
        /* 忽略静默刷新失败 */
      } finally {
        if (!cancelled) setReloading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefVersion, seed]);

  // 冷启动引导：工作台就绪、未关注任何子领域且未引导过时弹一次（localStorage 记忆）
  const [showColdstart, setShowColdstart] = useState(false);
  useEffect(() => {
    if (activeTab !== 'workbench' || loading) return;
    const mine = dataByTab.workbench?.mine;
    if (mine && mine.has_followed_subfields === false && localStorage.getItem('pp_coldstart_done') !== '1') {
      setShowColdstart(true);
    }
  }, [activeTab, loading, dataByTab]);

  const bumpSeed = useCallback(() => {
    seedRef.current += 1;
    setSeed(seedRef.current);
  }, []);

  const tabs: { key: DashboardTab; label: string; icon: React.ReactNode }[] = [
    { key: 'workbench', label: t('dash.tabWorkbench'), icon: <BookOpen className="w-4 h-4" /> },
    { key: 'briefing', label: t('dash.tabBriefing'), icon: <Newspaper className="w-4 h-4" /> },
    { key: 'stack', label: t('dash.tabStack'), icon: <Layers className="w-4 h-4" /> },
    { key: 'prefs', label: t('dash.tabPrefs'), icon: <SlidersHorizontal className="w-4 h-4" /> },
  ];

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white mb-1">
          {tabs.find((tb) => tb.key === activeTab)?.label || t('dash.tabWorkbench')}
        </h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm">
          {activeTab === 'workbench'
            ? t('dash.subtitleWorkbench')
            : activeTab === 'briefing'
            ? t('dash.subtitleBriefing')
            : activeTab === 'stack'
            ? t('dash.subtitleStack')
            : t('dash.subtitlePrefs')}
        </p>
      </div>

      {/* 模块页签（对齐系统页「分开 + 切换」样式） */}
      <div className="border-b border-gray-200 dark:border-gray-700 mb-6 overflow-x-auto">
        <nav className="flex gap-4 sm:gap-6 min-w-max" role="tablist" aria-label={t('dash.tabWorkbench')}>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              role="tab"
              aria-selected={activeTab === tab.key}
              onClick={() => switchTab(tab.key)}
              className={`flex items-center gap-1.5 sm:gap-2 px-1 py-2 sm:py-3 text-xs sm:text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.key
                  ? 'text-primary-600 dark:text-primary-400 border-primary-600'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 border-transparent'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-6">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : error ? (
        <div className="text-center py-12">
          <p className="text-gray-500 dark:text-gray-400 mb-4">{error}</p>
          <button onClick={() => loadTab(activeTab, seed)} className="text-primary-600 hover:underline text-sm">{t('common.retry')}</button>
        </div>
      ) : (
        <div className="space-y-8" role="tabpanel">
          {activeTab === 'workbench' && dataByTab.workbench?.today_read && dataByTab.workbench?.mine && (
            <TodayRead
              data={dataByTab.workbench as DashboardData}
              reloading={reloading}
              seed={seed}
              onRefresh={bumpSeed}
              onFollowedChanged={() => setFollowVersion((v) => v + 1)}
            />
          )}
          {activeTab === 'briefing' && dataByTab.briefing?.briefing && (
            <Briefing data={dataByTab.briefing as DashboardData} />
          )}
          {activeTab === 'stack' && dataByTab.stack?.mine && (
            <MyStack data={dataByTab.stack as DashboardData} />
          )}
          {activeTab === 'prefs' && (
            <>
              <SuggestionBar onFollowChanged={() => setFollowVersion((v) => v + 1)} />
              <FollowSubfields version={followVersion} />
              <FollowKeywords version={followVersion} />
              <PreferencesPanel />
            </>
          )}
        </div>
      )}

      {showColdstart && (
        <ColdStartWizard
          onDone={() => {
            setShowColdstart(false);
            setFollowVersion((v) => v + 1);
            bumpSeed();
          }}
        />
      )}
    </Layout>
  );
}

/** ① 研究工作台：进行中选题进度 + 今日值得读（反馈闭环）+ 新论文展开 + 稍后读队列 */
function TodayRead({ data, reloading, seed, onRefresh, onFollowedChanged }: {
  data: DashboardData;
  reloading: boolean;
  seed: number;
  onRefresh: () => void;
  onFollowedChanged: () => void;
}) {
  const { t } = useLanguage();
  const { toast } = useToast();
  const [readBusy, setReadBusy] = useState<string | null>(null);
  const [fbBusy, setFbBusy] = useState<string | null>(null);
  const mine = data.mine as MineData;

  // 「看过了」：记录阅读历史，后端下次推荐自动排除该论文（入口在卡片「不感兴趣」菜单顶部）
  const handleMarkRead = async (p: PaperCardType) => {
    if (readBusy) return;
    setReadBusy(p.id);
    try {
      await personalApi.recordReading(p.id);
      toast(t('dash.readDone'), 'success');
      onRefresh();
    } catch {
      toast(t('pref.hideFailed'), 'error');
    } finally {
      setReadBusy(null);
    }
  };

  // 推荐反馈闭环：👍 多推这类（关注其关键词/子领域） / 👎 少推这类（屏蔽其关键词/子领域）
  const handleFeedback = async (p: PaperCardType, action: 'more' | 'less') => {
    if (fbBusy) return;
    setFbBusy(`${p.id}:${action}`);
    try {
      const res = await personalApi.recommendFeedback(p.id, action);
      if (!res.applied) {
        toast(t('dash.feedbackAlready'), 'warning');
      } else {
        const typeLabel = t(res.entity_type === 'keyword' ? 'pref.type.keyword' : 'pref.type.subfield');
        toast(
          t(action === 'more' ? 'dash.feedbackMoreDone' : 'dash.feedbackLessDone', { type: typeLabel, value: res.entity_value || '' }),
          'success',
        );
        if (action === 'less') await refreshPreferences();
        onRefresh();
      }
    } catch {
      toast(t('dash.feedbackFailed'), 'error');
    } finally {
      setFbBusy(null);
    }
  };

  return (
    <section>
      <ProjectProgressStrip projects={mine.topic_projects} />

      <div className="flex items-center gap-2 mb-3">
        <BookOpen className="w-5 h-5 text-primary-600" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('dash.todayRead')}</h2>
        {reloading && <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400" />}
        <span className="text-xs text-gray-400">
          {mine.has_followed_subfields ? t('dash.recommendByScoreFollowed') : t('dash.recommendByScore')}
        </span>
        <button
          onClick={onRefresh}
          title={t('dash.shuffle')}
          className="ml-auto flex items-center gap-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline shrink-0"
        >
          <RefreshCw className={`w-3 h-3 ${reloading ? 'animate-spin' : ''}`} />
          {t('dash.shuffle')}
        </button>
      </div>
      {!mine.has_followed_subfields && (
        <p className="text-xs text-gray-400 mb-2">
          {t('dash.followHintPre')}
          <Link href="/dashboard?tab=prefs" className="text-primary-600 mx-1 hover:underline">{t('dash.tabPrefs')}</Link>
          {t('dash.followHintPost')}
        </p>
      )}
      {mine.watch_subfield_count != null && mine.watch_subfield_count > 0 && (
        <p className="text-xs text-gray-400 mb-2">
          <Link href="/search" className="text-primary-600 hover:underline">
            {t('dash.watchSubfieldNew', { n: mine.watch_subfield_count })}
          </Link>
        </p>
      )}
      <div className={`grid grid-cols-1 gap-4 sm:gap-6 transition-opacity duration-300 ${reloading ? 'opacity-50' : 'opacity-100'}`}>
        {data.today_read.map((p, idx) => (
          <div key={`${p.id}-${seed}`} className="pp-fade-slide-in" style={{ animationDelay: `${idx * 60}ms` }}>
            {p.reason && (
              <div className="flex items-center gap-2 mb-1.5">
                <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300">
                  <Sparkles className="w-3 h-3" />
                  {p.reason.label}
                </span>
                <button
                  onClick={() => handleFeedback(p, 'more')}
                  disabled={!!fbBusy}
                  title={t('dash.moreLikeThis')}
                  aria-label={t('dash.moreLikeThis')}
                  className="text-[11px] leading-none text-gray-400 hover:text-green-600 dark:hover:text-green-400 transition-colors disabled:opacity-50"
                >
                  👍
                </button>
                <button
                  onClick={() => handleFeedback(p, 'less')}
                  disabled={!!fbBusy}
                  title={t('dash.lessLikeThis')}
                  aria-label={t('dash.lessLikeThis')}
                  className="text-[11px] leading-none text-gray-400 hover:text-red-500 transition-colors disabled:opacity-50"
                >
                  👎
                </button>
              </div>
            )}
            <PaperCard
              paper={p}
              surface="dashboard_today_read"
              onMarkRead={() => handleMarkRead(p)}
              markReadBusy={readBusy === p.id}
            />
          </div>
        ))}
        {data.today_read.length === 0 && (
          <div className="text-sm text-gray-400">
            <p className="mb-2">{t('dash.noRecommendPapers')}</p>
            <Link href="/dashboard?tab=prefs" className="inline-flex items-center gap-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
              <SlidersHorizontal className="w-3.5 h-3.5" />
              {t('dash.goPrefs')}
            </Link>
          </div>
        )}
      </div>

      <WatchNewList onPapersRead={onRefresh} />
      <ReadLaterQueue onQueueChanged={onRefresh} />
    </section>
  );
}

/** 进行中选题进度条：五步向导进度 + 文献集精读统计（打通"读论文"与"写论文"） */
function ProjectProgressStrip({ projects }: { projects: DashboardData['mine']['topic_projects'] }) {
  const { t } = useLanguage();
  const active = projects.slice(0, 3);
  if (active.length === 0) return null;
  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {active.map((tp) => (
        <Link
          key={tp.id}
          href={`/topics?project=${tp.id}`}
          className="group flex items-center gap-2 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 px-3 py-1.5 hover:border-blue-400 dark:hover:border-blue-600 transition-colors"
        >
          <Target className="w-3.5 h-3.5 text-blue-500 shrink-0" />
          <span className="max-w-[180px] sm:max-w-[260px] truncate text-xs font-medium text-blue-800 dark:text-blue-200">
            {tp.title}
          </span>
          <span className="shrink-0 rounded-full bg-blue-100 dark:bg-blue-900/50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700 dark:text-blue-300">
            {t('dash.stepN', { n: tp.current_step ?? 1 })}
          </span>
          {(tp.paper_count ?? 0) > 0 && (
            <span className="shrink-0 text-[10px] text-blue-600/80 dark:text-blue-300/80">
              {t('dash.paperStat', { n: tp.paper_count ?? 0, m: tp.read_count ?? 0 })}
            </span>
          )}
        </Link>
      ))}
    </div>
  );
}

/** 关注子领域近 30 天新论文：就地展开（替代跳搜索页重拼筛选），支持「全部标为看过」 */
function WatchNewList({ onPapersRead }: { onPapersRead: () => void }) {
  const { t } = useLanguage();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [papers, setPapers] = useState<PaperCardType[]>([]);
  const [total, setTotal] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    dashboardApi.getWatchNewPapers()
      .then((res) => {
        if (!cancelled) {
          setPapers(res.papers || []);
          setTotal(res.total);
          setLoaded(true);
        }
      })
      .catch(() => { if (!cancelled) setLoaded(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, reloadKey]);

  const markAllRead = async () => {
    if (busy || papers.length === 0) return;
    setBusy(true);
    try {
      await personalApi.recordReadingBatch(papers.map((p) => p.id));
      toast(t('dash.watchNewAllReadDone'), 'success');
      onPapersRead();
      setReloadKey((k) => k + 1);
    } catch {
      toast(t('pref.hideFailed'), 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-6 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors"
      >
        <Clock className="w-4 h-4 text-primary-500" />
        <span className="font-medium">{t('dash.watchNewTitle')}</span>
        <ChevronDown className={`w-4 h-4 ml-auto transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="px-4 pb-4">
          {loading && !loaded ? (
            <p className="text-xs text-gray-400 py-3">
              <Loader2 className="w-3.5 h-3.5 animate-spin inline-block mr-1" />
              {t('dash.watchNewLoading')}
            </p>
          ) : papers.length === 0 ? (
            <p className="text-xs text-gray-400 py-3">{t('dash.watchNewEmpty')}</p>
          ) : (
            <>
              <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 mb-3">
                <span className="text-xs text-gray-400">{t('dash.watchNewTotal', { n: total })}</span>
                <button
                  onClick={markAllRead}
                  disabled={busy}
                  className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline disabled:opacity-50"
                >
                  {busy ? <Loader2 className="w-3 h-3 animate-spin inline-block mr-1" /> : <Check className="w-3 h-3 inline-block mr-1" />}
                  {t('dash.watchNewAllRead')}
                </button>
              </div>
              <div className="space-y-4">
                {papers.map((p) => (
                  <PaperCard key={p.id} paper={p} surface="dashboard_watch_new" />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** 稍后读队列：论文卡片的时钟图标加入；这里集中消费（标记已读并移出 / 仅移出） */
function ReadLaterQueue({ onQueueChanged }: { onQueueChanged: () => void }) {
  const { t } = useLanguage();
  const { toast } = useToast();
  const [papers, setPapers] = useState<PaperCardType[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await personalApi.getReadLaterPapers();
      setPapers(res.papers || []);
    } catch { /* 静默失败，不阻塞页签 */ }
    setLoaded(true);
  }, []);

  useEffect(() => { load(); }, [load]);

  const done = async (pid: string) => {
    setBusyId(pid);
    try {
      await personalApi.recordReading(pid);
      await personalApi.toggleReadLater(pid); // 队列中 -> 移出
      toast(t('dash.readLaterDoneMsg'), 'success');
      await load();
      onQueueChanged();
    } catch {
      toast(t('pref.hideFailed'), 'error');
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (pid: string) => {
    setBusyId(pid);
    try {
      await personalApi.toggleReadLater(pid);
      await load();
    } catch {
      toast(t('pref.hideFailed'), 'error');
    } finally {
      setBusyId(null);
    }
  };

  if (!loaded) return null;

  return (
    <div className="mt-6 rounded-lg border border-gray-200 dark:border-gray-700 px-4 py-3">
      <div className="flex items-center gap-2">
        <Clock className="w-4 h-4 text-amber-500" />
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('dash.readLaterTitle')}</h3>
        {papers.length > 0 && <span className="text-xs text-gray-400">{t('dash.readLaterCount', { n: papers.length })}</span>}
        <Link href="/read-later" className="ml-auto text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
          查看全部 →
        </Link>
      </div>
      {papers.length === 0 ? (
        <p className="text-xs text-gray-400 mt-2">{t('dash.readLaterEmpty')}</p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {papers.map((p) => (
            <li key={p.id} className="flex items-center gap-2">
              <Link href={`/paper/${p.id}`} className="flex-1 min-w-0 text-xs text-gray-600 dark:text-gray-400 hover:text-primary-600 line-clamp-1">
                {p.title}
              </Link>
              <button
                onClick={() => done(p.id)}
                disabled={busyId === p.id}
                title={t('dash.readLaterDone')}
                aria-label={t('dash.readLaterDone')}
                className="shrink-0 text-gray-400 hover:text-green-600 dark:hover:text-green-400 transition-colors disabled:opacity-50"
              >
                {busyId === p.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
              </button>
              <button
                onClick={() => remove(p.id)}
                disabled={busyId === p.id}
                title={t('dash.readLaterRemove')}
                aria-label={t('dash.readLaterRemove')}
                className="shrink-0 text-gray-300 dark:text-gray-600 hover:text-red-500 transition-colors disabled:opacity-50"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** 冷启动引导：首次进入工作台且未关注子领域时弹一次，选 ≥3 个方向开启个性化 */
function ColdStartWizard({ onDone }: { onDone: () => void }) {
  const { t } = useLanguage();
  const { toast } = useToast();
  const [distribution, setDistribution] = useState<Array<{ subfield: string; count: number }>>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { papersApi } = await import('@/lib/api');
        const stats = await papersApi.getSubfieldDistribution();
        setDistribution((stats.distribution || []).slice(0, 12));
      } catch { /* ignore */ }
    })();
  }, []);

  const toggle = (sf: string) =>
    setSelected((prev) => (prev.includes(sf) ? prev.filter((x) => x !== sf) : [...prev, sf]));

  const finish = () => {
    localStorage.setItem('pp_coldstart_done', '1');
    onDone();
  };

  const confirm = async () => {
    setSaving(true);
    try {
      const { personalApi } = await import('@/lib/api');
      await personalApi.setSubfields(selected);
      toast(t('dash.coldstart.done'), 'success');
      finish();
    } catch {
      toast(t('dash.coldstart.saveFailed'), 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-label={t('dash.coldstart.title')}>
      <div className="w-full max-w-md rounded-xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-xl p-5 sm:p-6">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles className="w-5 h-5 text-primary-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('dash.coldstart.title')}</h2>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">{t('dash.coldstart.subtitle')}</p>
        <div className="flex flex-wrap gap-2 mb-4 max-h-56 overflow-y-auto">
          {distribution.map((d) => {
            const activeSel = selected.includes(d.subfield);
            return (
              <button
                key={d.subfield}
                onClick={() => toggle(d.subfield)}
                className={`px-3 py-1.5 rounded-full text-xs border transition-colors ${
                  activeSel
                    ? 'bg-primary-600 text-white border-primary-600'
                    : 'bg-gray-50 dark:bg-gray-700/50 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:border-primary-300'
                }`}
              >
                {d.subfield}
                <span className={`ml-1 text-[10px] ${activeSel ? 'text-primary-200' : 'text-gray-400'}`}>{d.count}</span>
              </button>
            );
          })}
          {distribution.length === 0 && <p className="text-xs text-gray-400">{t('follow.empty')}</p>}
        </div>
        <div className="flex items-center justify-between">
          <button onClick={finish} className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
            {t('dash.coldstart.skip')}
          </button>
          <button
            onClick={confirm}
            disabled={saving || selected.length < 3}
            className="px-4 py-2 rounded-lg bg-primary-600 text-white text-sm disabled:opacity-50 hover:bg-primary-700 transition-colors"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : selected.length < 3 ? t('dash.coldstart.needMore', { n: 3 - selected.length }) : t('dash.coldstart.confirm')}
          </button>
        </div>
      </div>
    </div>
  );
}

/** ② 领域快讯：近 3 年热点 Top 5 + AI 摘要，「查看全部」跳趋势页 */
function Briefing({ data }: { data: DashboardData }) {
  const { t } = useLanguage();
  return (
    <section className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
      <div className="flex items-center gap-2 mb-3">
        <Newspaper className="w-5 h-5 text-red-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('dash.tabBriefing')}</h2>
        <span className="text-xs text-gray-400">{t('dash.briefingSubtitle')}</span>
        <Link
          href="/trends"
          className="ml-auto flex items-center gap-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline shrink-0"
        >
          {t('dash.viewAll')}
          <TrendingUp className="w-3 h-3" />
        </Link>
      </div>
      {data.briefing.ai_note && (
        <div className="mb-4 flex items-start gap-2 bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3 text-sm text-purple-800 dark:text-purple-300">
          <Sparkles className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{data.briefing.ai_note}</span>
        </div>
      )}
      <div className="space-y-2">
        {data.briefing.topics.map((topic, idx) => {
          const bt = topic as BriefingTopic;
          return (
            <div key={bt.topic} className="flex items-center justify-between gap-3 py-1.5 border-b border-gray-100 dark:border-gray-700 last:border-0">
              <div className="flex items-center gap-2 min-w-0">
                <span className="w-5 h-5 shrink-0 flex items-center justify-center bg-gray-100 dark:bg-gray-700 rounded text-xs font-bold text-gray-500">
                  {idx + 1}
                </span>
                <Link
                  href={`/search?search=${encodeURIComponent(bt.topic)}&search_field=keyword`}
                  className="truncate text-sm text-gray-800 dark:text-gray-200 hover:text-primary-600 dark:hover:text-primary-400"
                >
                  {bt.topic}
                </Link>
              </div>
              <div className="flex items-center gap-2 shrink-0 text-xs text-gray-500">
                <TopicSparkline series={bt.series} />
                <span>{trendIcon(bt.trend)}</span>
                <span className={`font-medium ${bt.growth_rate > 0.2 ? 'text-red-500' : bt.growth_rate < -0.1 ? 'text-blue-500' : 'text-gray-400'}`}>
                  {(bt.growth_rate * 100).toFixed(0)}%
                </span>
                <span className="hidden sm:inline">{t('dash.paperCount', { n: bt.paper_count })}</span>
              </div>
            </div>
          );
        })}
        {data.briefing.topics.length === 0 && (
          <div className="text-sm text-gray-400">
            <p className="mb-2">{t('dash.noTrendData')}</p>
            <Link href="/trends" className="inline-flex items-center gap-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
              {t('dash.viewAll')}
              <TrendingUp className="w-3 h-3" />
            </Link>
          </div>
        )}
      </div>
    </section>
  );
}

/** ③ 我的研究栈：收藏 + 最近 AI 分析 + 进行中选题 + 最近阅读入口 */
function MyStack({ data }: { data: DashboardData }) {
  const { t } = useLanguage();
  return (
    <section className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6" id="mine">
      <div className="flex items-center gap-2 mb-4">
        <Layers className="w-5 h-5 text-green-600" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('dash.tabStack')}</h2>
        <span className="text-xs text-gray-400">{t('dash.favoriteCount', { n: data.mine.favorite_count })}</span>
      </div>

      {/* 最新 AI 领域分析（trends 页生成，dashboard 后端已算好 summary/id，这里接线展示） */}
      {data.mine.latest_report_summary && data.mine.latest_report_id && (
        <div className="mb-6 flex items-start gap-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg border border-purple-200 dark:border-purple-800 p-3">
          <FileSearch className="w-5 h-5 text-purple-500 shrink-0 mt-0.5" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2 mb-1">
              <h3 className="text-sm font-medium text-gray-800 dark:text-gray-200">{t('dash.latestAiAnalysis')}</h3>
              <Link
                href="/trends"
                className="flex items-center gap-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline shrink-0"
              >
                {t('dash.viewAll')}
                <TrendingUp className="w-3 h-3" />
              </Link>
            </div>
            <p className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2">{data.mine.latest_report_summary}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {/* 收藏 */}
        <div>
          <h3 className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            <Bookmark className="w-4 h-4 text-yellow-500" /> {t('dash.recentFavorites')}
          </h3>
          {data.mine.favorites.length === 0 ? (
            <p className="text-xs text-gray-400">{t('dash.noFavorites')}</p>
          ) : (
            <ul className="space-y-1.5">
              {data.mine.favorites.slice(0, 5).map((p) => (
                <li key={p.id}>
                  <Link href={`/paper/${p.id}`} className="text-xs text-gray-600 dark:text-gray-400 hover:text-primary-600 line-clamp-1">
                    {p.title}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
        {/* 最近 AI 分析 */}
        <div>
          <h3 className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            <FileSearch className="w-4 h-4 text-purple-500" /> {t('dash.recentAnalyses')}
          </h3>
          {data.mine.recent_analyses.length === 0 ? (
            <p className="text-xs text-gray-400">{t('dash.noAnalyses')}</p>
          ) : (
            <ul className="space-y-1.5">
              {data.mine.recent_analyses.map((a) => (
                <li key={a.paper_id}>
                  <Link href={`/paper/${a.paper_id}#analysis`} className="text-xs text-gray-600 dark:text-gray-400 hover:text-primary-600 line-clamp-1">
                    {a.title || a.paper_id}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
        {/* 进行中选题 */}
        <div>
          <h3 className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            <Target className="w-4 h-4 text-blue-500" /> {t('dash.projectsInProgress')}
          </h3>
          {data.mine.topic_projects.length === 0 ? (
            <p className="text-xs text-gray-400">
              {t('dash.noProjectsPre')}<Link href="/topics" className="text-primary-600 mx-0.5 hover:underline">{t('nav.topics')}</Link>{t('dash.noProjectsPost')}
            </p>
          ) : (
            <ul className="space-y-1.5">
              {data.mine.topic_projects.map((tp) => (
                <li key={tp.id}>
                  <Link href={`/topics?project=${tp.id}`} className="text-xs text-gray-600 dark:text-gray-400 hover:text-primary-600 line-clamp-1">
                    {tp.title}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* 最近文献综述 */}
      <div className="border-t border-gray-100 dark:border-gray-700 pt-4 mb-6">
        <div className="flex items-center justify-between mb-2">
          <h3 className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
            <BookMarked className="w-4 h-4 text-purple-500" /> {t('dash.recentReviews')}
          </h3>
          <Link
            href="/topics"
            className="flex items-center gap-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline"
          >
            {t('dash.viewAll')}
            <BookMarked className="w-3 h-3" />
          </Link>
        </div>
        {data.mine.reviews.length === 0 ? (
          <p className="text-xs text-gray-400">
            {t('dash.noReviewsPre')}
            <Link href="/topics" className="text-primary-600 mx-0.5 hover:underline">{t('nav.topics')}</Link>
            {t('dash.noReviewsPost')}
          </p>
        ) : (
          <ul className="space-y-1.5">
            {data.mine.reviews.slice(0, 5).map((r) => (
              <li key={r.id}>
                <Link
                  href="/topics"
                  className="block text-xs text-gray-600 dark:text-gray-400 hover:text-primary-600"
                >
                  <span className="line-clamp-1">{r.topic}</span>
                  <span className="text-gray-400">
                    {t('dash.reviewRefCount', { n: r.paper_count })}{r.created_at ? ` · ${new Date(r.created_at).toLocaleDateString()}` : ''}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 最近阅读入口 */}
      <RecentReading />
    </section>
  );
}

/** 最近阅读历史（最近 5 条 + 查看全部），数据与 /reading 同源 */
function RecentReading() {
  const { t } = useLanguage();
  const [papers, setPapers] = useState<PaperCardType[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    personalApi.getReadingHistory()
      .then((res) => { if (!cancelled) setPapers(res.papers || []); })
      .catch(() => { /* 静默失败，不阻塞页签 */ })
      .finally(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, []);

  if (!loaded) return null;

  return (
    <div className="border-t border-gray-100 dark:border-gray-700 pt-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
          <History className="w-4 h-4 text-gray-500" /> {t('dash.recentReading')}
        </h3>
        <Link href="/reading" className="flex items-center gap-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
          {t('dash.viewAll')}
          <History className="w-3 h-3" />
        </Link>
      </div>
      {papers.length === 0 ? (
        <p className="text-xs text-gray-400">{t('dash.noReading')}</p>
      ) : (
        <ul className="space-y-1.5">
          {papers.slice(0, 5).map((p) => (
            <li key={p.id}>
              <Link href={`/paper/${p.id}`} className="text-xs text-gray-600 dark:text-gray-400 hover:text-primary-600 line-clamp-1">
                {p.title}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FollowSubfields({ version = 0 }: { version?: number }) {
  const { t } = useLanguage();
  const [subfields, setSubfields] = useState<string[]>([]);
  const [distribution, setDistribution] = useState<Array<{ subfield: string; count: number }>>([]);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const { personalApi, papersApi } = await import('@/lib/api');
        const [me, stats] = await Promise.all([
          personalApi.getSubfields(),
          papersApi.getSubfieldDistribution(),
        ]);
        setSubfields(me.subfields);
        setDistribution(stats.distribution);
      } catch { /* ignore */ }
      setLoaded(true);
    })();
  }, [version]);

  const toggle = async (sf: string) => {
    const next = subfields.includes(sf) ? subfields.filter((s) => s !== sf) : [...subfields, sf];
    setSubfields(next);
    setSaving(true);
    try {
      const { personalApi } = await import('@/lib/api');
      await personalApi.setSubfields(next);
    } catch { /* ignore */ }
    setSaving(false);
  };

  const sorted = distribution
    .filter((d) => !filter || d.subfield.toLowerCase().includes(filter.toLowerCase()))
    .sort((a, b) => b.count - a.count);

  if (!loaded) return null;

  return (
    <section className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6" id="follow-subfield">
      <div className="flex items-center gap-2 mb-3">
        <TrendingUp className="w-5 h-5 text-purple-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('follow.titleSubfield')}</h2>
        {saving && <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400" />}
        <span className="text-xs text-gray-400">{t('follow.subtitle')}</span>
      </div>
      {distribution.length > 10 && (
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t('follow.searchPlaceholder')}
          className="mb-3 w-full sm:w-64 px-3 py-1.5 text-xs border border-gray-200 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-purple-400"
        />
      )}
      <div className="flex flex-wrap gap-2">
        {sorted.map((d) => {
          const active = subfields.includes(d.subfield);
          return (
            <button
              key={d.subfield}
              onClick={() => toggle(d.subfield)}
              className={`px-3 py-1.5 rounded-full text-xs border transition-colors ${
                active
                  ? 'bg-primary-600 text-white border-primary-600'
                  : 'bg-gray-50 dark:bg-gray-700/50 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:border-primary-300'
              }`}
            >
              {d.subfield}
              <span className={`ml-1 text-[10px] ${active ? 'text-primary-200' : 'text-gray-400'}`}>
                {d.count}
              </span>
            </button>
          );
        })}
        {sorted.length === 0 && (
          <p className="text-sm text-gray-400">{t('follow.empty')}</p>
        )}
      </div>
    </section>
  );
}

function FollowKeywords({ version = 0 }: { version?: number }) {
  const { t } = useLanguage();
  const [keywords, setKeywords] = useState<string[]>([]);
  const [distribution, setDistribution] = useState<Array<{ keyword: string; count: number }>>([]);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const { personalApi, papersApi } = await import('@/lib/api');
        const [me, stats] = await Promise.all([
          personalApi.getKeywords(),
          papersApi.getKeywordDistribution(),
        ]);
        setKeywords(me.keywords);
        setDistribution(stats.distribution);
      } catch { /* ignore */ }
      setLoaded(true);
    })();
  }, [version]);

  const toggle = async (kw: string) => {
    const next = keywords.includes(kw) ? keywords.filter((k) => k !== kw) : [...keywords, kw];
    setKeywords(next);
    setSaving(true);
    try {
      const { personalApi } = await import('@/lib/api');
      await personalApi.setKeywords(next);
    } catch { /* ignore */ }
    setSaving(false);
  };

  const sorted = distribution
    .filter((d) => !filter || d.keyword.toLowerCase().includes(filter.toLowerCase()))
    .sort((a, b) => b.count - a.count);

  // 折叠：默认仅展示前 50 个高频词（已关注的始终可见），避免上百个 chips 刷屏
  const KEYWORD_PREVIEW_LIMIT = 50;
  const [expanded, setExpanded] = useState(false);
  const visible = expanded
    ? sorted
    : [
        ...sorted.filter((d) => keywords.includes(d.keyword)),
        ...sorted.filter((d) => !keywords.includes(d.keyword)).slice(0, KEYWORD_PREVIEW_LIMIT),
      ];
  const hiddenCount = Math.max(0, sorted.length - visible.length);

  if (!loaded) return null;

  return (
    <section className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6" id="follow-keyword">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles className="w-5 h-5 text-amber-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('follow.titleKeyword')}</h2>
        {saving && <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400" />}
        <span className="text-xs text-gray-400">{t('follow.subtitle')}</span>
      </div>
      {distribution.length > 15 && (
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t('follow.searchPlaceholder')}
          className="mb-3 w-full sm:w-64 px-3 py-1.5 text-xs border border-gray-200 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-amber-400"
        />
      )}
      <div className="flex flex-wrap gap-2">
        {visible.map((d) => {
          const active = keywords.includes(d.keyword);
          return (
            <button
              key={d.keyword}
              onClick={() => toggle(d.keyword)}
              className={`px-3 py-1.5 rounded-full text-xs border transition-colors ${
                active
                  ? 'bg-amber-500 text-white border-amber-500'
                  : 'bg-gray-50 dark:bg-gray-700/50 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:border-amber-300'
              }`}
            >
              {d.keyword}
              <span className={`ml-1 text-[10px] ${active ? 'text-amber-200' : 'text-gray-400'}`}>
                {d.count}
              </span>
            </button>
          );
        })}
        {sorted.length === 0 && (
          <p className="text-sm text-gray-400">{t('follow.empty')}</p>
        )}
      </div>
      {hiddenCount > 0 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-3 text-xs text-amber-600 dark:text-amber-400 hover:underline"
        >
          {expanded ? '收起' : `展开其余 ${hiddenCount} 个关键词`}
        </button>
      )}
    </section>
  );
}

function SuggestionBar({ onFollowChanged }: { onFollowChanged?: () => void }) {
  const { t } = useLanguage();
  const { toast } = useToast();
  const [subfields, setSubfields] = useState<string[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<{ subfields: Array<{ name: string; reason: string; paper_count: number }>; keywords: Array<{ name: string; reason: string; paper_count: number }> } | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [followed, setFollowed] = useState<Set<string>>(new Set());

  const fetchAll = async () => {
    try {
      const { personalApi } = await import('@/lib/api');
      const [me, kw, sug] = await Promise.all([
        personalApi.getSubfields(),
        personalApi.getKeywords(),
        personalApi.getSuggestions(),
      ]);
      setSubfields(me.subfields);
      setKeywords(kw.keywords);
      setSuggestions(sug);
    } catch { /* ignore */ }
    setLoaded(true);
  };

  useEffect(() => { fetchAll(); }, []);

  const handleFollowSubfield = async (name: string) => {
    const next = [...subfields, name];
    setSubfields(next);
    setFollowed((prev) => new Set(prev).add(`sf:${name}`));
    try {
      const { personalApi } = await import('@/lib/api');
      await personalApi.setSubfields(next);
      toast(t('follow.titleSubfield') + ': ' + name, 'success');
      onFollowChanged?.();
    } catch { /* ignore */ }
  };

  const handleFollowKeyword = async (name: string) => {
    const next = [...keywords, name];
    setKeywords(next);
    setFollowed((prev) => new Set(prev).add(`kw:${name}`));
    try {
      const { personalApi } = await import('@/lib/api');
      await personalApi.setKeywords(next);
      toast(t('follow.titleKeyword') + ': ' + name, 'success');
      onFollowChanged?.();
    } catch { /* ignore */ }
  };

  if (!loaded || !suggestions) return null;

  const items = [
    ...suggestions.subfields
      .filter((s) => !subfields.includes(s.name) && !followed.has(`sf:${s.name}`))
      .map((s) => ({ ...s, type: 'subfield' as const })),
    ...suggestions.keywords
      .filter((s) => !keywords.includes(s.name) && !followed.has(`kw:${s.name}`))
      .map((s) => ({ ...s, type: 'keyword' as const })),
  ];
  if (items.length === 0) return null;

  return (
    <section className="bg-gradient-to-r from-purple-50 to-amber-50 dark:from-purple-900/20 dark:to-amber-900/20 rounded-lg border border-purple-200 dark:border-purple-800 p-4 sm:p-6">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles className="w-5 h-5 text-purple-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('follow.suggestions')}</h2>
      </div>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <button
            key={`${item.type}:${item.name}`}
            onClick={() => item.type === 'subfield' ? handleFollowSubfield(item.name) : handleFollowKeyword(item.name)}
            className={`group px-3 py-1.5 rounded-full text-xs border transition-all cursor-pointer ${
              item.type === 'subfield'
                ? 'bg-white dark:bg-gray-800 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-700 hover:bg-purple-100 dark:hover:bg-purple-900/40 hover:shadow-sm'
                : 'bg-white dark:bg-gray-800 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-700 hover:bg-amber-100 dark:hover:bg-amber-900/40 hover:shadow-sm'
            }`}
          >
            <Plus className="w-3 h-3 inline-block mr-1 opacity-0 group-hover:opacity-100 transition-opacity" />
            {item.name}
            <span className="ml-1 text-[10px] text-gray-400">
              {item.type === 'subfield' ? t('follow.paperCount', { count: item.paper_count }) : item.reason}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
