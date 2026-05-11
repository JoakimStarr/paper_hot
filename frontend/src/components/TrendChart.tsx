'use client';

import React from 'react';
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
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { useTheme } from '@/contexts/ThemeContext';

interface TrendChartProps {
  topics: TrendingTopic[];
}

export default function TrendChart({ topics }: TrendChartProps) {
  const { isDark } = useTheme();
  const axisColor = isDark ? '#9ca3af' : '#6b7280';
  const gridColor = isDark ? '#374151' : '#e5e7eb';
  const tooltipStyle = isDark ? { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' } : undefined;

  const chartData = topics.map((topic) => ({
    name: topic.topic,
    papers: topic.paper_count,
    growth: (topic.growth_rate * 100).toFixed(1),
  }));

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border border-gray-200 dark:border-gray-700 transition-colors duration-300">
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-6">Trending Topics</h2>
      
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
              name="Paper Count"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {topics.map((topic) => (
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
              <span className="text-gray-600 dark:text-gray-400">Papers: {topic.paper_count}</span>
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
          </div>
        ))}
      </div>
    </div>
  );
}