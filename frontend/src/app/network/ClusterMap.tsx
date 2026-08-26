'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { Loader2, Map as MapIcon } from 'lucide-react';
import { papersApi } from '@/lib/api';
import { TopicClustersResponse, TopicCluster } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

const PALETTE = [
  '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6',
  '#f97316', '#6366f1', '#84cc16', '#06b6d4', '#d946ef', '#eab308', '#22c55e',
  '#f43f5e', '#0ea5e9', '#a855f7', '#64748b',
];

interface Props { onData?: () => void }

export default function ClusterMap({ onData }: Props) {
  const { t } = useLanguage();
  const router = useRouter();
  const [data, setData] = useState<TopicClustersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<TopicCluster | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await papersApi.getTopicClusters();
        if (!alive) return;
        setData(res);
        onData?.();
      } catch (e: unknown) {
        if (alive) setError(e instanceof Error ? e.message : 'load failed');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const labelById = useMemo(() => {
    const m = new Map<number, TopicCluster>();
    data?.clusters.forEach(c => m.set(c.id, c));
    return m;
  }, [data]);

  if (loading) {
    return (
      <div className="flex flex-col justify-center items-center py-12 text-gray-500">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600 mb-3" />
        <div className="text-sm">{t('net.clusterComputing')}</div>
      </div>
    );
  }
  if (error || !data || data.clusters.length === 0) {
    return <div className="text-center py-10 text-sm text-red-500">{error || t('net.noData')}</div>;
  }

  return (
    <div className="grid lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
        <div className="flex items-center gap-2 mb-2 text-xs text-gray-500 dark:text-gray-400">
          <MapIcon className="w-4 h-4" />
          {t('net.clusterScatterHint').replace('{total}', String(data.total))}
        </div>
        <ResponsiveContainer width="100%" height={520}>
          <ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#8884" />
            <XAxis type="number" dataKey="x" domain={[0, 100]} hide />
            <YAxis type="number" dataKey="y" domain={[0, 100]} hide />
            <Tooltip
              content={({ payload }) => {
                const p = payload?.[0]?.payload as { title: string; id: string } | undefined;
                if (!p) return null;
                const c = Array.from(labelById.values()).find(c => c.points.some(pt => pt.id === p.id));
                return (
                  <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg px-3 py-2 max-w-xs">
                    <div className="text-xs font-medium text-gray-900 dark:text-white line-clamp-3">{p.title}</div>
                    {c && <div className="text-[10px] text-primary-600 mt-1">{c.label}</div>}
                  </div>
                );
              }}
            />
            {data.clusters.map((c, i) => (
              <Scatter
                key={c.id}
                name={c.label}
                data={c.points}
                fill={PALETTE[i % PALETTE.length]}
                fillOpacity={selected ? (selected.id === c.id ? 0.95 : 0.15) : 0.75}
                className="cursor-pointer"
                onClick={(pt: unknown) => {
                  const pid = (pt as { id?: string })?.id;
                  if (pid) router.push(`/paper/${pid}`);
                }}
              />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <div className="space-y-2">
        <div className="text-xs text-gray-500 dark:text-gray-400 px-1">
          {t('net.clusterLegend')}（{data.k}）
        </div>
        <div className="space-y-1.5 max-h-[560px] overflow-y-auto pr-1">
          {data.clusters.map((c, i) => (
            <button
              key={c.id}
              onClick={() => setSelected(selected?.id === c.id ? null : c)}
              className={`w-full text-left px-3 py-2 rounded-lg border transition-colors ${
                selected?.id === c.id
                  ? 'border-primary-400 bg-primary-50 dark:bg-primary-900/30'
                  : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/60'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: PALETTE[i % PALETTE.length] }} />
                <span className="text-xs font-medium text-gray-900 dark:text-white truncate flex-1">{c.label}</span>
                <span className="text-[10px] text-gray-400 shrink-0">{c.size}{t('net.papersUnit')}</span>
              </div>
              <div className="text-[10px] text-gray-400 mt-0.5 pl-4.5 flex items-center gap-2">
                <span>{c.year_range}</span>
              </div>
            </button>
          ))}
        </div>
        {selected && (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div className="text-xs font-semibold text-gray-900 dark:text-white mb-2">{t('net.representativePapers')}</div>
            <div className="space-y-1.5">
              {selected.representative_papers.map(p => (
                <button
                  key={p.id}
                  onClick={() => router.push(`/paper/${p.id}`)}
                  className="block w-full text-left text-xs text-gray-600 dark:text-gray-300 hover:text-primary-600 line-clamp-2"
                >
                  • {p.title}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
