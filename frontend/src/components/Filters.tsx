'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useLanguage } from '@/contexts/LanguageContext';
import { papersApi, FilterStatistics } from '@/lib/api';
import { ArrowUpDown } from 'lucide-react';

interface FiltersProps {
  minScore: number | null;
  selectedTopic: string[];
  selectedJournal: string[];
  sortBy: string;
  sortOrder: string;
  showBookmarksOnly: boolean;
  onMinScoreChange: (score: number | null) => void;
  onTopicChange: (topics: string[]) => void;
  onJournalChange: (journals: string[]) => void;
  onSortByChange: (sort: string) => void;
  onSortOrderToggle: () => void;
  onBookmarksChange: (v: boolean) => void;
}

const scoreThresholds = [0.5, 0.6, 0.7, 0.8, 0.9];

const SORT_OPTIONS = [
  { value: 'date', label: '发布时间' },
  { value: 'score', label: '评分' },
  { value: 'title', label: '标题' },
];

function MultiSelect({ options, selected, onChange, label, counts }: {
  options: string[];
  selected: string[];
  onChange: (v: string[]) => void;
  label: string;
  counts: Record<string, number>;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const toggle = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter(v => v !== value));
    } else {
      onChange([...selected, value]);
    }
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="border border-gray-300 rounded-md px-2.5 py-1.5 text-xs bg-white outline-none focus:ring-1 focus:ring-primary-500 min-w-[120px] text-left"
      >
        {selected.length > 0 ? `${label} (${selected.length})` : label}
      </button>
      {open && (
        <div className="absolute z-20 mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-y-auto min-w-[200px]">
          {options.map((opt) => (
            <label
              key={opt}
              className="flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-gray-50 cursor-pointer"
            >
              <input
                type="checkbox"
                checked={selected.includes(opt)}
                onChange={() => toggle(opt)}
                className="rounded"
              />
              <span className="flex-1">{opt}</span>
              <span className="text-gray-400">({counts[opt] || 0})</span>
            </label>
          ))}
          {selected.length > 0 && (
            <button
              onClick={() => onChange([])}
              className="w-full text-center py-1.5 text-xs text-primary-600 hover:bg-gray-50 border-t"
            >
              清除
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function Filters({
  minScore,
  selectedTopic,
  selectedJournal,
  sortBy,
  sortOrder,
  showBookmarksOnly,
  onMinScoreChange,
  onTopicChange,
  onJournalChange,
  onSortByChange,
  onSortOrderToggle,
  onBookmarksChange,
}: FiltersProps) {
  const { t } = useLanguage();
  const [stats, setStats] = useState<FilterStatistics | null>(null);

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

  const getCount = (type: keyof FilterStatistics, key: string): number => {
    if (!stats) return 0;
    const counts = stats[type] as Record<string, number>;
    return counts?.[key] || 0;
  };

  const journals = stats
    ? Object.entries(stats.journal_counts)
        .sort((a, b) => b[1] - a[1])
        .map(([name]) => name)
    : [];

  const topics = stats
    ? Object.entries(stats.subfield_counts)
        .sort((a, b) => b[1] - a[1])
        .map(([name]) => name)
    : [];

  const hasActiveFilters = minScore || selectedTopic.length > 0 || selectedJournal.length > 0;

  return (
    <div className="bg-white rounded-lg shadow-md p-4 mb-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <MultiSelect
            options={topics}
            selected={selectedTopic}
            onChange={onTopicChange}
            label="专题筛选"
            counts={stats ? (stats.subfield_counts as Record<string, number>) : {}}
          />

          <MultiSelect
            options={journals}
            selected={selectedJournal}
            onChange={onJournalChange}
            label={t('filters.allJournals')}
            counts={stats ? (stats.journal_counts as Record<string, number>) : {}}
          />

          <div>
            <select
              value={minScore || ''}
              onChange={(e) => onMinScoreChange(e.target.value ? parseFloat(e.target.value) : null)}
              className="border border-gray-300 rounded-md px-2.5 py-1.5 text-xs bg-white outline-none focus:ring-1 focus:ring-primary-500"
            >
              <option value="">{t('filters.anyScore')} ({stats?.total_papers || 0})</option>
              {scoreThresholds.map((score) => (
                <option key={score} value={score}>≥ {(score * 100).toFixed(0)}% ({getCount('score_counts', score.toFixed(1))})</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1">
            <ArrowUpDown className="w-3 h-3 text-gray-400" />
            <select
              value={sortBy}
              onChange={(e) => onSortByChange(e.target.value)}
              className="border border-gray-300 rounded-md px-2 py-1.5 text-xs bg-white outline-none focus:ring-1 focus:ring-primary-500"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <button
              onClick={onSortOrderToggle}
              className="px-2 py-1.5 border border-gray-300 rounded-md text-xs bg-white hover:bg-gray-50 text-gray-500"
            >
              {sortOrder === 'desc' ? '↓' : '↑'}
            </button>
          </div>

          <label className="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showBookmarksOnly}
              onChange={(e) => onBookmarksChange(e.target.checked)}
              className="rounded"
            />
            仅看收藏
          </label>

          {hasActiveFilters && (
            <button
              onClick={() => {
                onMinScoreChange(null);
                onTopicChange([]);
                onJournalChange([]);
              }}
              className="text-xs text-primary-600 hover:text-primary-700 underline"
            >
              {t('filters.clearAll')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}