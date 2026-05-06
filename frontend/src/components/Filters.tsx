'use client';

import React, { useState, useEffect } from 'react';
import { useLanguage } from '@/contexts/LanguageContext';
import { papersApi, FilterStatistics } from '@/lib/api';

interface FiltersProps {
  minScore: number | null;
  selectedDiscipline: string | null;
  selectedJournal: string | null;
  onMinScoreChange: (score: number | null) => void;
  onDisciplineChange: (discipline: string | null) => void;
  onJournalChange: (journal: string | null) => void;
}

const scoreThresholds = [0.5, 0.6, 0.7, 0.8, 0.9];
const journals = ['经济研究', '管理世界', '经济学（季刊）', '世界经济', '中国工业经济', '美国经济评论'];

export default function Filters({
  minScore,
  selectedDiscipline,
  selectedJournal,
  onMinScoreChange,
  onDisciplineChange,
  onJournalChange,
}: FiltersProps) {
  const { t } = useLanguage();
  const [stats, setStats] = useState<FilterStatistics | null>(null);

  // 获取筛选统计数据
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await papersApi.getFilterStatistics();
        setStats(data);
      } catch (error) {
        console.error('Error fetching filter statistics:', error);
      }
    };

    fetchStats();
  }, []);

  // 获取数量的辅助函数
  const getCount = (type: keyof FilterStatistics, key: string): number => {
    if (!stats) return 0;
    const counts = stats[type] as Record<string, number>;
    return counts?.[key] || 0;
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('filters.title')}</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            {t('filters.discipline')}
          </label>
          <select
            value={selectedDiscipline || ''}
            onChange={(e) => onDisciplineChange(e.target.value || null)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">{t('filters.allDisciplines')}</option>
            <option value="AI">{t('filters.ai')} ({getCount('discipline_counts', 'AI')})</option>
            <option value="经济学">{t('filters.economics')} ({getCount('discipline_counts', '经济学')})</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            {t('filters.journal')}
          </label>
          <select
            value={selectedJournal || ''}
            onChange={(e) => onJournalChange(e.target.value || null)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">{t('filters.allJournals')}</option>
            {journals.map((journal) => (
              <option key={journal} value={journal}>
                {journal} ({getCount('journal_counts', journal)})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            {t('filters.minScore')}
          </label>
          <select
            value={minScore || ''}
            onChange={(e) => onMinScoreChange(e.target.value ? parseFloat(e.target.value) : null)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">{t('filters.anyScore')}</option>
            {scoreThresholds.map((score) => (
              <option key={score} value={score}>
                {`≥ ${(score * 100).toFixed(0)}%`} ({getCount('score_counts', `≥ ${(score * 100).toFixed(0)}%`)})
              </option>
            ))}
          </select>
        </div>
      </div>

      {(minScore || selectedDiscipline || selectedJournal) && (
        <div className="mt-4 flex items-center gap-2 flex-wrap">
          <span className="text-sm text-gray-600">{t('filters.activeFilters')}</span>
          {selectedDiscipline && (
            <span className="bg-primary-100 text-primary-800 text-xs px-2 py-1 rounded">
              {t('filters.discipline')}: {selectedDiscipline === 'AI' ? t('filters.ai') : t('filters.economics')}
            </span>
          )}
          {selectedJournal && (
            <span className="bg-primary-100 text-primary-800 text-xs px-2 py-1 rounded">
              {t('filters.journal')}: {selectedJournal}
            </span>
          )}
          {minScore && (
            <span className="bg-primary-100 text-primary-800 text-xs px-2 py-1 rounded">
              {t('filters.minScore')}: ≥{(minScore * 100).toFixed(0)}%
            </span>
          )}
          <button
            onClick={() => {
              onMinScoreChange(null);
              onDisciplineChange(null);
              onJournalChange(null);
            }}
            className="text-sm text-primary-600 hover:text-primary-700 underline"
          >
            {t('filters.clearAll')}
          </button>
        </div>
      )}
    </div>
  );
}
