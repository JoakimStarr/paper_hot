'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { Loader2, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { papersApi } from '@/lib/api';
import { KeywordTrendsResponse } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

const PALETTE = [
  '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899',
  '#14b8a6', '#f97316', '#6366f1', '#84cc16', '#06b6d4', '#d946ef',
];

const TREND_STYLE: Record<string, { icon: typeof TrendingUp; cls: string }> = {
  emerging: { icon: TrendingUp, cls: 'text-green-600 bg-green-50 dark:bg-green-900/30' },
  declining: { icon: TrendingDown, cls: 'text-red-500 bg-red-50 dark:bg-red-900/30' },
  stable: { icon: Minus, cls: 'text-gray-500 bg-gray-100 dark:bg-gray-700/40' },
};

export default function TrendChart() {
  const { t } = useLanguage();
  const [data, setData] = useState<KeywordTrendsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await papersApi.getKeywordTrends(12);
        if (alive) setData(res);
      } catch (e: unknown) {
        if (alive) setError(e instanceof Error ? e.message : 'load failed');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const chartData = useMemo(() => {
    if (!data) return [];
    const byYear = new Map<string, Record<string, number | string>>();
    data.years.forEach(y => byYear.set(y, { year: y }));
    data.series.forEach(s => s.yearly.forEach(({ year, count }) => {
      const row = byYear.get(year);
      if (row) row[s.name] = count;
    }));
    return Array.from(byYear.values()).sort((a, b) => String(a.year).localeCompare(String(b.year)));
  }, [data]);

  if (loading) {
    return <div className="flex justify-center py-12"><Loader2 className="w-8 h-8 animate-spin text-primary-600" /></div>;
  }
  if (error || !data || data.series.length === 0) {
    return <div className="text-center py-10 text-sm text-red-500">{error || t('net.noData')}</div>;
  }

  const toggle = (name: string) => {
    setHidden(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1.5">
        {data.series.map((s, i) => {
          const st = TREND_STYLE[s.trend] ?? TREND_STYLE.stable;
          const Icon = st.icon;
          const off = hidden.has(s.name);
          return (
            <button
              key={s.name}
              onClick={() => toggle(s.name)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border transition-colors ${
                off ? 'opacity-40 border-gray-200 dark:border-gray-700' : 'border-gray-300 dark:border-gray-600'
              } bg-white dark:bg-gray-800`}
            >
              <span className="w-2 h-2 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
              <span className="text-gray-900 dark:text-white font-medium max-w-[140px] truncate">{s.name}</span>
              <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full ${st.cls}`}>
                <Icon className="w-3 h-3" />
                {t(`net.trend_${s.trend}`)}
              </span>
            </button>
          );
        })}
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
        <ResponsiveContainer width="100%" height={420}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#8884" />
            <XAxis dataKey="year" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
            <Tooltip />
            <Legend onClick={(e: any) => e?.dataKey && toggle(String(e.dataKey))} wrapperStyle={{ fontSize: 12 }} />
            {data.series.map((s, i) => (
              <Line
                key={s.name}
                type="monotone"
                dataKey={s.name}
                hide={hidden.has(s.name)}
                stroke={PALETTE[i % PALETTE.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
        <div className="text-[11px] text-gray-400 mt-1">{t('net.trendHint')}</div>
      </div>
    </div>
  );
}
