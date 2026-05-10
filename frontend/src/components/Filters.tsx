'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useLanguage } from '@/contexts/LanguageContext';
import { papersApi, FilterStatistics } from '@/lib/api';
import { Search, ArrowUpDown, X } from 'lucide-react';

interface FiltersProps {
  minScore: number | null;
  selectedDiscipline: string | null;
  selectedJournal: string | null;
  searchQuery: string;
  searchField: string;
  sortBy: string;
  sortOrder: string;
  onMinScoreChange: (score: number | null) => void;
  onDisciplineChange: (discipline: string | null) => void;
  onJournalChange: (journal: string | null) => void;
  onSearchChange: (query: string) => void;
  onSearchSubmit: (query: string) => void;
  onSearchFieldChange: (field: string) => void;
  onSortByChange: (sort: string) => void;
  onSortOrderToggle: () => void;
}

const scoreThresholds = [0.5, 0.6, 0.7, 0.8, 0.9];

const SEARCH_FIELDS = [
  { value: 'title', label: '标题' },
  { value: 'author', label: '作者' },
  { value: 'keyword', label: '关键词' },
  { value: 'abstract', label: '摘要' },
];

const SORT_OPTIONS = [
  { value: 'date', label: '发布时间' },
  { value: 'score', label: '评分' },
  { value: 'title', label: '标题' },
];

export default function Filters({
  minScore,
  selectedDiscipline,
  selectedJournal,
  searchQuery,
  searchField,
  sortBy,
  sortOrder,
  onMinScoreChange,
  onDisciplineChange,
  onJournalChange,
  onSearchChange,
  onSearchSubmit,
  onSearchFieldChange,
  onSortByChange,
  onSortOrderToggle,
}: FiltersProps) {
  const { t } = useLanguage();
  const [stats, setStats] = useState<FilterStatistics | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

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

  useEffect(() => {
    if (searchOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [searchOpen]);

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

  const disciplines = stats ? Object.keys(stats.discipline_counts) : [];

  const hasActiveFilters = minScore || selectedDiscipline || selectedJournal || searchQuery;

  return (
    <div className="bg-white rounded-lg shadow-md p-4 mb-6">
      {searchOpen && (
        <div className="mb-3 flex items-center gap-2">
          <div className="flex-1 flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2 border border-gray-200">
            <Search className="w-4 h-4 text-gray-400 shrink-0" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  onSearchSubmit(searchQuery);
                } else if (e.key === 'Escape') {
                  setSearchOpen(false);
                  onSearchChange('');
                  onSearchSubmit('');
                }
              }}
              placeholder="输入关键词搜索，回车确认..."
              className="flex-1 bg-transparent text-sm outline-none"
            />
            <select
              value={searchField}
              onChange={(e) => onSearchFieldChange(e.target.value)}
              className="text-xs bg-white border border-gray-200 rounded px-2 py-0.5 shrink-0 outline-none"
            >
              {SEARCH_FIELDS.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>
            {searchQuery && (
              <button onClick={() => { onSearchChange(''); onSearchSubmit(''); }} className="p-0.5 hover:bg-gray-200 rounded">
                <X className="w-3 h-3 text-gray-400" />
              </button>
            )}
          </div>
          <button
            onClick={() => { setSearchOpen(false); onSearchChange(''); onSearchSubmit(''); }}
            className="text-xs text-gray-400 hover:text-gray-600 px-2"
          >
            取消
          </button>
        </div>
      )}

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <div>
            <select
              value={selectedDiscipline || ''}
              onChange={(e) => onDisciplineChange(e.target.value || null)}
              className="border border-gray-300 rounded-md px-2.5 py-1.5 text-xs bg-white outline-none focus:ring-1 focus:ring-primary-500"
            >
              <option value="">{t('filters.allDisciplines')} ({stats?.total_papers || 0})</option>
              {disciplines.map((d) => (
                <option key={d} value={d}>{d} ({getCount('discipline_counts', d)})</option>
              ))}
            </select>
          </div>

          <div>
            <select
              value={selectedJournal || ''}
              onChange={(e) => onJournalChange(e.target.value || null)}
              className="border border-gray-300 rounded-md px-2.5 py-1.5 text-xs bg-white outline-none focus:ring-1 focus:ring-primary-500"
            >
              <option value="">{t('filters.allJournals')} ({stats?.total_papers || 0})</option>
              {journals.map((journal) => (
                <option key={journal} value={journal}>{journal} ({getCount('journal_counts', journal)})</option>
              ))}
            </select>
          </div>

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

          {hasActiveFilters && (
            <button
              onClick={() => {
                onMinScoreChange(null);
                onDisciplineChange(null);
                onJournalChange(null);
                onSearchChange('');
                onSearchSubmit('');
                setSearchOpen(false);
              }}
              className="text-xs text-primary-600 hover:text-primary-700 underline"
            >
              {t('filters.clearAll')}
            </button>
          )}
        </div>

        <button
          onClick={() => setSearchOpen(!searchOpen)}
          className={`p-2 rounded-lg transition-colors ${
            searchQuery ? 'bg-primary-100 text-primary-600' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
          }`}
          title="搜索"
        >
          <Search className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}