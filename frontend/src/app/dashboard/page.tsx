'use client';

import React, { useState, useEffect, useCallback, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import SkeletonCard from '@/components/SkeletonCard';
import { useToast } from '@/components/Toast';
import { dashboardApi, DashboardData, personalApi } from '@/lib/api';
import { reportPageContext } from '@/lib/assistantBus';
import { usePreferences } from '@/lib/usePreferences';
import { useLanguage } from '@/contexts/LanguageContext';
import { PaperCard as PaperCardType, TrendingTopic } from '@/types/paper';
import {
  BookOpen, Newspaper, Layers, Sparkles, TrendingUp, TrendingDown,
  Minus, Bookmark, FileSearch, Target, Loader2, EyeOff, Plus, X, History, SlidersHorizontal, BookMarked,
  RefreshCw,
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

  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 「不感兴趣」屏蔽版本号：新增/删除屏蔽项后重取工作台，保证「今日值得读」即时生效
  const { version: prefVersion } = usePreferences();

  const load = useCallback(async (s: number) => {
    setLoading(true);
    setError(null);
    try {
      setData(await dashboardApi.getDashboard(s));
    } catch (e) {
      setError(e instanceof Error ? e.message : t('dash.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 关注变更版本号：SuggestionBar/FollowSubfields/FollowKeywords 变化时触发子组件重取
  const [followVersion, setFollowVersion] = useState(0);

  // 页内 Link 跳转到 /dashboard?tab=xxx 时同步激活页签
  useEffect(() => {
    const p = searchParams.get('tab');
    if (p && (VALID_TABS as string[]).includes(p)) {
      setActiveTab(p as DashboardTab);
    }
  }, [searchParams]);

  // 屏蔽项变化 / 「换一批」「看过了」时静默重取工作台；reloading 仅在顶部小节显示轻量加载指示
  const [reloading, setReloading] = useState(false);
  const [seed, setSeed] = useState(0);
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
        const fresh = await dashboardApi.getDashboard(seed);
        if (!cancelled) setData(fresh);
      } catch {
        /* 忽略静默刷新失败 */
      } finally {
        if (!cancelled) setReloading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefVersion, seed]);

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
        <nav className="flex gap-4 sm:gap-6 min-w-max">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => {
                setActiveTab(tab.key);
                reportPageContext({ tab: tab.key });
              }}
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
      ) : error || !data ? (
        <div className="text-center py-12">
          <p className="text-gray-500 dark:text-gray-400 mb-4">{error || t('dash.noData')}</p>
          <button onClick={() => load(seed)} className="text-primary-600 hover:underline text-sm">{t('common.retry')}</button>
        </div>
      ) : (
        <div className="space-y-8">
          {activeTab === 'workbench' && (
            <TodayRead data={data} reloading={reloading} onRefresh={() => setSeed((s) => s + 1)} />
          )}
          {activeTab === 'briefing' && <Briefing data={data} />}
          {activeTab === 'stack' && <MyStack data={data} />}
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
    </Layout>
  );
}

/** ① 研究工作台：今日值得读 */
function TodayRead({ data, reloading, onRefresh }: { data: DashboardData; reloading: boolean; onRefresh: () => void }) {
  const { t } = useLanguage();
  const { toast } = useToast();
  const [readBusy, setReadBusy] = useState<string | null>(null);
  const mine = data.mine as MineData;

  // 「看过了」：记录阅读历史，后端下次推荐自动排除该论文
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

  return (
    <section>
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
      <div className="grid grid-cols-1 gap-4 sm:gap-6">
        {data.today_read.map((p) => (
          <div key={p.id}>
            {p.reason && (
              <div className="flex items-center gap-2 mb-1.5">
                <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300">
                  <Sparkles className="w-3 h-3" />
                  {p.reason.label}
                </span>
                <button
                  onClick={() => handleMarkRead(p)}
                  disabled={readBusy === p.id}
                  className="text-[11px] text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors disabled:opacity-50"
                >
                  {readBusy === p.id ? <Loader2 className="w-3 h-3 animate-spin inline-block" /> : t('dash.markRead')}
                </button>
              </div>
            )}
            <PaperCard paper={p} surface="dashboard_today_read" />
          </div>
        ))}
        {data.today_read.length === 0 && (
          <p className="text-sm text-gray-400">{t('dash.noRecommendPapers')}</p>
        )}
      </div>
    </section>
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
          <p className="text-sm text-gray-400">{t('dash.noTrendData')}</p>
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
        {sorted.map((d) => {
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

const PREF_TYPES: Array<{ type: 'subfield' | 'journal' | 'keyword' | 'author'; labelKey: string }> = [
  { type: 'subfield', labelKey: 'pref.type.subfield' },
  { type: 'journal', labelKey: 'pref.type.journal' },
  { type: 'keyword', labelKey: 'pref.type.keyword' },
  { type: 'author', labelKey: 'pref.type.author' },
];

/** ⑤「不感兴趣」屏蔽管理：按类型增删领域/期刊/关键词/作者，全局列表过滤生效。 */
function PreferencesPanel() {
  const { t } = useLanguage();
  const { toast } = useToast();
  const { items, add, remove } = usePreferences();
  const [activeType, setActiveType] = useState<'subfield' | 'journal' | 'keyword' | 'author'>('subfield');
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);

  const activeItems = items.filter((p) => p.entity_type === activeType);

  const handleAdd = async () => {
    const value = input.trim();
    if (!value) return;
    setBusy(true);
    try {
      await add(activeType, value);
      setInput('');
      toast(t('pref.hideMsg'), 'success');
    } catch {
      toast(t('pref.hideFailed'), 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (value: string) => {
    try {
      await remove(activeType, value);
      toast(t('pref.unhideMsg'), 'success');
    } catch {
      toast(t('pref.unhideFailed'), 'error');
    }
  };

  return (
    <section className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6" id="hide">
      <div className="flex items-center gap-2 mb-3">
        <EyeOff className="w-5 h-5 text-red-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('pref.title')}</h2>
        <span className="text-xs text-gray-400">{t('pref.subtitle')}</span>
      </div>

      {/* 类型切换 */}
      <div className="flex flex-wrap gap-2 mb-4">
        {PREF_TYPES.map(({ type, labelKey }) => (
          <button
            key={type}
            onClick={() => setActiveType(type)}
            className={`px-3 py-1.5 rounded-full text-xs border transition-colors ${
              activeType === type
                ? 'bg-red-500 text-white border-red-500'
                : 'bg-gray-50 dark:bg-gray-700/50 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:border-red-300'
            }`}
          >
            {t(labelKey)}
          </button>
        ))}
      </div>

      {/* 已有屏蔽项 */}
      {activeItems.length === 0 ? (
        <p className="text-sm text-gray-400 mb-4">{t('pref.empty')}</p>
      ) : (
        <div className="flex flex-wrap gap-2 mb-4">
          {activeItems.map((p) => (
            <span
              key={`${p.entity_type}:${p.entity_value}`}
              className="inline-flex items-center gap-1.5 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-xs px-2.5 py-1 rounded-full border border-red-200 dark:border-red-800"
            >
              <span className="max-w-[180px] truncate">{p.entity_value}</span>
              <button
                onClick={() => handleRemove(p.entity_value)}
                className="hover:bg-red-100 dark:hover:bg-red-900/50 rounded-full p-0.5"
                title={t('pref.remove')}
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* 手动新增 */}
      <div className="flex items-center gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleAdd(); }}
          placeholder={t('pref.addPlaceholder', { type: t(activeType === 'subfield' ? 'pref.type.subfield' : activeType === 'journal' ? 'pref.type.journal' : activeType === 'keyword' ? 'pref.type.keyword' : 'pref.type.author') })}
          className="flex-1 min-w-0 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 text-sm outline-none focus:ring-2 focus:ring-red-400 focus:border-transparent"
        />
        <button
          onClick={handleAdd}
          disabled={busy || !input.trim()}
          className="flex items-center gap-1 px-3 py-2 rounded-lg bg-red-500 text-white text-sm disabled:opacity-50 hover:bg-red-600 transition-colors"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          {t('pref.add')}
        </button>
      </div>
    </section>
  );
}
