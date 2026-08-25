'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import SkeletonCard from '@/components/SkeletonCard';
import { dashboardApi, DashboardData } from '@/lib/api';
import {
  BookOpen, Newspaper, Layers, Sparkles, TrendingUp, TrendingDown,
  Minus, Bookmark, FileSearch, Target, Loader2,
} from 'lucide-react';

const trendIcon = (trend: string) =>
  trend === 'rising' ? (
    <TrendingUp className="w-3.5 h-3.5 text-red-500" />
  ) : trend === 'declining' ? (
    <TrendingDown className="w-3.5 h-3.5 text-blue-500" />
  ) : (
    <Minus className="w-3.5 h-3.5 text-gray-400" />
  );

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await dashboardApi.getDashboard());
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white mb-1">研究工作台</h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm">
          今天该看什么、领域在发生什么、我的研究进展到哪 —— 一页回答
        </p>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-6">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : error || !data ? (
        <div className="text-center py-12">
          <p className="text-gray-500 dark:text-gray-400 mb-4">{error || '暂无数据'}</p>
          <button onClick={load} className="text-primary-600 hover:underline text-sm">重试</button>
        </div>
      ) : (
        <div className="space-y-8">
          {/* ① 今日值得读 */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <BookOpen className="w-5 h-5 text-primary-600" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">今日值得读</h2>
              <span className="text-xs text-gray-400">
                按综合评分{data.mine.has_followed_subfields ? ' + 你关注的子领域' : ''}推荐
              </span>
            </div>
            {!data.mine.has_followed_subfields && (
              <p className="text-xs text-gray-400 mb-2">
                提示：在
                <Link href="/dashboard#follow" className="text-primary-600 mx-1 hover:underline">下方关注子领域</Link>
                后，这里会优先推荐你关注的方向。
              </p>
            )}
            <div className="grid grid-cols-1 gap-4 sm:gap-6">
              {data.today_read.map((p) => (
                <PaperCard key={p.id} paper={p} />
              ))}
              {data.today_read.length === 0 && (
                <p className="text-sm text-gray-400">暂无推荐论文</p>
              )}
            </div>
          </section>

          {/* ② 领域快讯 */}
          <section className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
            <div className="flex items-center gap-2 mb-3">
              <Newspaper className="w-5 h-5 text-red-500" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">领域快讯</h2>
              <span className="text-xs text-gray-400">近 8 周热点趋势 Top 5</span>
            </div>
            {data.briefing.ai_note && (
              <div className="mb-4 flex items-start gap-2 bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3 text-sm text-purple-800 dark:text-purple-300">
                <Sparkles className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{data.briefing.ai_note}</span>
              </div>
            )}
            <div className="space-y-2">
              {data.briefing.topics.map((topic, idx) => (
                <div key={topic.topic} className="flex items-center justify-between gap-3 py-1.5 border-b border-gray-100 dark:border-gray-700 last:border-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="w-5 h-5 shrink-0 flex items-center justify-center bg-gray-100 dark:bg-gray-700 rounded text-xs font-bold text-gray-500">
                      {idx + 1}
                    </span>
                    <Link
                      href={`/search?search=${encodeURIComponent(topic.topic)}&search_field=keyword`}
                      className="truncate text-sm text-gray-800 dark:text-gray-200 hover:text-primary-600 dark:hover:text-primary-400"
                    >
                      {topic.topic}
                    </Link>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 text-xs text-gray-500">
                    <span>{trendIcon(topic.trend)}</span>
                    <span className={`font-medium ${topic.growth_rate > 0.2 ? 'text-red-500' : topic.growth_rate < -0.1 ? 'text-blue-500' : 'text-gray-400'}`}>
                      {(topic.growth_rate * 100).toFixed(0)}%
                    </span>
                    <span className="hidden sm:inline">{topic.paper_count} 篇</span>
                  </div>
                </div>
              ))}
              {data.briefing.topics.length === 0 && (
                <p className="text-sm text-gray-400">近期暂无趋势数据</p>
              )}
            </div>
          </section>

          {/* ③ 我的研究栈 */}
          <section className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6" id="mine">
            <div className="flex items-center gap-2 mb-4">
              <Layers className="w-5 h-5 text-green-600" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">我的研究栈</h2>
              <span className="text-xs text-gray-400">收藏 {data.mine.favorite_count} 篇</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* 收藏 */}
              <div>
                <h3 className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  <Bookmark className="w-4 h-4 text-yellow-500" /> 最近收藏
                </h3>
                {data.mine.favorites.length === 0 ? (
                  <p className="text-xs text-gray-400">还没有收藏，点论文卡片的书签试试</p>
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
                  <FileSearch className="w-4 h-4 text-purple-500" /> 最近 AI 分析
                </h3>
                {data.mine.recent_analyses.length === 0 ? (
                  <p className="text-xs text-gray-400">还没有分析过论文，列表页点「AI 分析」即可</p>
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
                  <Target className="w-4 h-4 text-blue-500" /> 进行中的选题
                </h3>
                {data.mine.topic_projects.length === 0 ? (
                  <p className="text-xs text-gray-400">
                    还没有选题，去<Link href="/topics" className="text-primary-600 mx-0.5 hover:underline">选题中心</Link>验证一个吧
                  </p>
                ) : (
                  <ul className="space-y-1.5">
                    {data.mine.topic_projects.map((tp) => (
                      <li key={tp.id}>
                        <Link href="/topics?tab=projects" className="text-xs text-gray-600 dark:text-gray-400 hover:text-primary-600 line-clamp-1">
                          {tp.title}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </section>

          {/* ④ 关注子领域（驱动推荐） */}
          <FollowSubfields />
        </div>
      )}
    </Layout>
  );
}

function FollowSubfields() {
  const [subfields, setSubfields] = useState<string[]>([]);
  const [allOptions, setAllOptions] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { personalApi, papersApi } = await import('@/lib/api');
        const [me, stats] = await Promise.all([
          personalApi.getSubfields(),
          papersApi.getSubfieldDistribution(),
        ]);
        setSubfields(me.subfields);
        setAllOptions(stats.distribution.map((d) => d.subfield));
      } catch { /* ignore */ }
      setLoaded(true);
    })();
  }, []);

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

  if (!loaded) return null;

  return (
    <section className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6" id="follow">
      <div className="flex items-center gap-2 mb-3">
        <TrendingUp className="w-5 h-5 text-purple-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">关注子领域</h2>
        {saving && <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400" />}
        <span className="text-xs text-gray-400">选择后驱动「今日值得读」个性化推荐</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {allOptions.map((sf) => {
          const active = subfields.includes(sf);
          return (
            <button
              key={sf}
              onClick={() => toggle(sf)}
              className={`px-3 py-1.5 rounded-full text-xs border transition-colors ${
                active
                  ? 'bg-primary-600 text-white border-primary-600'
                  : 'bg-gray-50 dark:bg-gray-700/50 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:border-primary-300'
              }`}
            >
              {sf}
            </button>
          );
        })}
      </div>
    </section>
  );
}
