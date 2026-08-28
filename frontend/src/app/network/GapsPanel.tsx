'use client';

import { useEffect, useState } from 'react';
import { ExternalLink, Loader2, Target } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { topicsApi } from '@/lib/api';
import { ResearchGapsResponse } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

export default function GapsPanel() {
  const { t } = useLanguage();
  const router = useRouter();

  /** 一键开题：空白组合 -> 研究工作台项目（跨页直达，创建后进入五步向导） */
  const toValidator = async (source: string, target: string) => {
    try {
      const p = await topicsApi.createTopicProject({
        title: `交叉研究：${source} 与 ${target} 的结合`,
        source_type: 'gap',
        source_ref: `${source}×${target}`,
      });
      router.push(`/topics?project=${p.id}`);
    } catch { /* ignore */ }
  };
  const [data, setData] = useState<ResearchGapsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await topicsApi.getResearchGaps(10);
        if (alive) setData(res);
      } catch (e: unknown) {
        if (alive) setError(e instanceof Error ? e.message : 'load failed');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  if (loading) {
    return <div className="flex justify-center py-12"><Loader2 className="w-8 h-8 animate-spin text-primary-600" /></div>;
  }
  if (error || !data || data.gaps.length === 0) {
    return <div className="text-center py-10 text-sm text-red-500">{error || t('net.noData')}</div>;
  }

  const maxScore = Math.max(...data.gaps.map(g => g.gap_score), 0.0001);

  return (
    <div className="space-y-3">
      <div className="text-xs text-gray-500 dark:text-gray-400 px-1">{t('net.gapHint')}</div>
      <div className="grid md:grid-cols-2 gap-3">
        {data.gaps.map((g, i) => (
          <div key={`${g.source}-${g.target}`} className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="text-sm font-medium text-gray-900 dark:text-white leading-snug">
                <span className="text-primary-700 dark:text-primary-300">{g.source}</span>
                <span className="mx-1.5 text-gray-400">×</span>
                <span className="text-emerald-700 dark:text-emerald-300">{g.target}</span>
              </div>
              <a
                href={`https://kns.cnki.net/kns8s/defaultresult/index?kw=${encodeURIComponent(`${g.source} ${g.target}`)}`}
                target="_blank"
                rel="noopener noreferrer"
                title={t('net.verifyOnCnki')}
                className="shrink-0 p-1.5 rounded-md text-gray-400 hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/40 transition-colors"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
              <button
                onClick={() => toValidator(g.source, g.target)}
                title={t('net.gapToValidator')}
                className="shrink-0 p-1.5 rounded-md text-gray-400 hover:text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/40 transition-colors"
              >
                <Target className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs text-gray-500 dark:text-gray-400 mb-2">
              <span>{t('net.gapSourceCount')}: <b className="text-gray-800 dark:text-gray-200">{g.source_count}</b></span>
              <span>{t('net.gapTargetCount')}: <b className="text-gray-800 dark:text-gray-200">{g.target_count}</b></span>
              <span>{t('net.gapCooccur')}: <b className="text-gray-800 dark:text-gray-200">{g.cooccurrence}</b></span>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-primary-500 to-emerald-500 rounded-full"
                  style={{ width: `${Math.round((g.gap_score / maxScore) * 100)}%` }}
                />
              </div>
              <span className="text-[11px] font-semibold text-primary-600 shrink-0">
                {t('net.gapScore')} {g.gap_score.toFixed(2)}
              </span>
              <span className="text-[11px] text-gray-300">#{i + 1}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
