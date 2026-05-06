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

interface TrendChartProps {
  topics: TrendingTopic[];
}

export default function TrendChart({ topics }: TrendChartProps) {
  const chartData = topics.map((topic) => ({
    name: topic.topic,
    papers: topic.paper_count,
    growth: (topic.growth_rate * 100).toFixed(1),
  }));

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-6">Trending Topics</h2>
      
      <div className="mb-6">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
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
            className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
          >
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-gray-900">{topic.topic}</h3>
              {topic.trend === 'rising' && (
                <TrendingUp className="w-5 h-5 text-green-600" />
              )}
              {topic.trend === 'declining' && (
                <TrendingDown className="w-5 h-5 text-red-600" />
              )}
              {topic.trend === 'stable' && (
                <Minus className="w-5 h-5 text-gray-600" />
              )}
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">Papers: {topic.paper_count}</span>
              <span
                className={`font-medium ${
                  topic.growth_rate > 0
                    ? 'text-green-600'
                    : topic.growth_rate < 0
                    ? 'text-red-600'
                    : 'text-gray-600'
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
