'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { TrendingTopic } from '@/types/paper';
import { TrendingUp, TrendingDown, Minus, ChevronUp, ChevronDown, FileSearch, Sparkles, Loader2 } from 'lucide-react';
import { useTheme } from '@/contexts/ThemeContext';
import { useLanguage } from '@/contexts/LanguageContext';
import { papersApi } from '@/lib/api';

interface TrendChartProps {
  topics: TrendingTopic[];
}

const COLLAPSE_STORAGE_KEY = 'trendchart_collapse_state';

export default function TrendChart({ topics }: TrendChartProps) {
  const { isDark } = useTheme();
  const { t } = useLanguage();
  const router = useRouter();
  const [isCollapsed, setIsCollapsed] = useState(false);
  // P2-13b：每个话题的「AI 解读这段趋势」状态
  const [explainations, setExplainations] = useState<Record<string, { text: string; loading: boolean; error?: boolean }>>({});
  const axisColor = isDark ? '#9ca3af' : '#6b7280';
  const gridColor = isDark ? '#374151' : '#e5e7eb';
  const tooltipStyle = isDark ? { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' } : undefined;

  useEffect(() => {
    const savedState = localStorage.getItem(COLLAPSE_STORAGE_KEY);
    if (savedState) {
      setIsCollapsed(savedState === 'true');
    }
  }, []);

  const toggleCollapse = () => {
    const newState = !isCollapsed;
    setIsCollapsed(newState);
    localStorage.setItem(COLLAPSE_STORAGE_KEY, String(newState));
  };

  /** P2-13b：AI 解读单个话题的趋势（懒加载，点一次拉一次）。 */
  const handleExplain = async (topicName: string) => {
    const cur = explainations[topicName];
    if (cur?.loading) return;
    // 已展开则收起
    if (cur && !cur.loading && !cur.error) {
      setExplainations((prev) => {
        const next = { ...prev };
        delete next[topicName];
        return next;
      });
      return;
    }
    setExplainations((prev) => ({ ...prev, [topicName]: { text: '', loading: true } }));
    try {
      const res = await papersApi.explainTrend(topicName);
      setExplainations((prev) => ({ ...prev, [topicName]: { text: res.explanation, loading: false } }));
    } catch {
      setExplainations((prev) => ({ ...prev, [topicName]: { text: '', loading: false, error: true } }));
    }
  };

  /** P2-13b：查看相关论文（按关键词搜索）。 */
  const handleViewPapers = (topicName: string) => {
    router.push(`/search?search=${encodeURIComponent(topicName)}&search_field=keyword`);
  };

  const chartData = topics.map((topic) => ({
    name: topic.topic,
    papers: topic.paper_count,
    growth: (topic.growth_rate * 100).toFixed(1),
  }));

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border border-gray-200 dark:border-gray-700 transition-colors duration-300">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('trends.hotTopics')}</h2>
        <button
          onClick={toggleCollapse}
          className="flex items-center gap-1 px-2 py-1.5 text-sm text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
          title={isCollapsed ? '展开' : '收起'}
        >
          {isCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          {isCollapsed ? '展开' : '收起'}
        </button>
      </div>
      {!isCollapsed && (<>
      
      <div className="mb-6">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis dataKey="name" tick={{ fill: axisColor }} />
            <YAxis tick={{ fill: axisColor }} />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend />
            <Line
              type="monotone"
              dataKey="papers"
              stroke="#3b82f6"
              strokeWidth={2}
              name={t('trends.paperCount')}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {topics.map((topic) => {
          const explainState = explainations[topic.topic];
          return (
            <div
              key={topic.topic}
              className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold text-gray-900 dark:text-white">{topic.topic}</h3>
                {topic.trend === 'rising' && (
                  <TrendingUp className="w-5 h-5 text-green-600" />
                )}
                {topic.trend === 'declining' && (
                  <TrendingDown className="w-5 h-5 text-red-600" />
                )}
                {topic.trend === 'stable' && (
                  <Minus className="w-5 h-5 text-gray-600 dark:text-gray-400" />
                )}
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600 dark:text-gray-400">{t('trends.paperCount')}: {topic.paper_count}</span>
                <span
                  className={`font-medium ${
                    topic.growth_rate > 0
                      ? 'text-green-600'
                      : topic.growth_rate < 0
                      ? 'text-red-600'
                      : 'text-gray-600 dark:text-gray-400'
                  }`}
                >
                  {topic.growth_rate > 0 ? '+' : ''}
                  {(topic.growth_rate * 100).toFixed(1)}%
                </span>
              </div>

              {/* P2-13b：查看相关论文 + AI 解读这段趋势 */}
              <div className="flex items-center gap-2 mt-3 pt-2.5 border-t border-gray-100 dark:border-gray-700">
                <button
                  onClick={() => handleViewPapers(topic.topic)}
                  className="flex items-center gap-1 text-xs text-primary-600 dark:text-primary-400 hover:underline"
                >
                  <FileSearch className="w-3.5 h-3.5" />
                  查看相关论文
                </button>
                <button
                  onClick={() => handleExplain(topic.topic)}
                  className={`ml-auto flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border transition-colors ${
                    explainState && !explainState.error
                      ? 'bg-purple-50 dark:bg-purple-900/30 border-purple-200 dark:border-purple-800 text-purple-700 dark:text-purple-300'
                      : 'border-gray-200 dark:border-gray-600 text-gray-500 hover:border-purple-300 hover:text-purple-600'
                  }`}
                >
                  {explainState?.loading ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Sparkles className="w-3 h-3" />
                  )}
                  AI 解读
                </button>
              </div>

              {explainState?.loading && (
                <p className="mt-2 text-xs text-gray-400">正在解读趋势…</p>
              )}
              {explainState?.error && (
                <p className="mt-2 text-xs text-red-400">解读失败（AI 未配置或网络异常）</p>
              )}
              {explainState?.text && !explainState.loading && (
                <div className="mt-2 bg-purple-50 dark:bg-purple-900/20 rounded-lg p-2.5 text-xs leading-relaxed text-gray-700 dark:text-gray-300">
                  <Sparkles className="w-3 h-3 inline mr-1 text-purple-500" />
                  {explainState.text}
                </div>
              )}
            </div>
          );
        })}
      </div>
      </>)}
    </div>
  );
}