'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useLanguage } from '@/contexts/LanguageContext';
import { papersApi, FilterStatistics } from '@/lib/api';
import { ArrowUpDown, Filter, X, ChevronDown } from 'lucide-react';

interface FiltersProps {
  minScore: number | null;
  selectedSubfield: string[];
  selectedCnkiSubject: string[];
  selectedJournal: string[];
  sortBy: string;
  sortOrder: string;
  showBookmarksOnly: boolean;
  onMinScoreChange: (score: number | null) => void;
  onSubfieldChange: (subfields: string[]) => void;
  onCnkiSubjectChange: (subjects: string[]) => void;
  onJournalChange: (journals: string[]) => void;
  onSortByChange: (sort: string) => void;
  onSortOrderToggle: () => void;
  onBookmarksChange: (v: boolean) => void;
}

const scoreThresholds = [0.5, 0.6, 0.7, 0.8, 0.9];

const SORT_OPTIONS = [
  { value: 'date', label: '按期数排序' },
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
        className="border border-gray-300 dark:border-gray-600 rounded-md px-2.5 py-1.5 text-xs bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 outline-none focus:ring-1 focus:ring-primary-500 min-w-[120px] text-left"
      >
        {selected.length > 0 ? `${label} (${selected.length})` : label}
      </button>
      {open && (
        <div className="absolute z-20 mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-lg max-h-48 overflow-y-auto min-w-[240px]">
          {options.map((opt) => (
            <label
              key={opt}
              className="flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer text-gray-900 dark:text-gray-100"
            >
              <input
                type="checkbox"
                checked={selected.includes(opt)}
                onChange={() => toggle(opt)}
                className="rounded"
              />
              <span className="flex-1 truncate">{opt}</span>
              <span className="text-gray-400 dark:text-gray-500 shrink-0">({counts[opt] || 0})</span>
            </label>
          ))}
          {selected.length > 0 && (
            <button
              onClick={() => onChange([])}
              className="w-full text-center py-1.5 text-xs text-primary-600 dark:text-primary-400 hover:bg-gray-50 dark:hover:bg-gray-700 border-t dark:border-gray-700"
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
  selectedSubfield,
  selectedCnkiSubject,
  selectedJournal,
  sortBy,
  sortOrder,
  showBookmarksOnly,
  onMinScoreChange,
  onSubfieldChange,
  onCnkiSubjectChange,
  onJournalChange,
  onSortByChange,
  onSortOrderToggle,
  onBookmarksChange,
}: FiltersProps) {
  const { t } = useLanguage();
  const [stats, setStats] = useState<FilterStatistics | null>(null);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);

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

  const subfields = stats
    ? Object.entries(stats.subfield_counts)
        .sort((a, b) => b[1] - a[1])
        .map(([name]) => name)
    : [];

  const cnkiSubjects = stats
    ? Object.entries(stats.cnki_subject_counts || {})
        .sort((a, b) => b[1] - a[1])
        .map(([name]) => name)
    : [];

  const hasActiveFilters = minScore || selectedSubfield.length > 0 || selectedCnkiSubject.length > 0 || selectedJournal.length > 0;
  const activeFilterCount = selectedSubfield.length + selectedCnkiSubject.length + selectedJournal.length + (minScore ? 1 : 0);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-3 sm:p-4 mb-6 transition-colors">
      {/* Mobile Filter Toggle */}
      <div className="md:hidden mb-3">
        <button
          onClick={() => setMobileFiltersOpen(!mobileFiltersOpen)}
          className="flex items-center justify-between w-full px-3 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg text-sm text-gray-700 dark:text-gray-300"
        >
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4" />
            <span>筛选条件</span>
            {activeFilterCount > 0 && (
              <span className="px-1.5 py-0.5 bg-primary-600 text-white text-xs rounded-full">
                {activeFilterCount}
              </span>
            )}
          </div>
          <ChevronDown className={`w-4 h-4 transition-transform ${mobileFiltersOpen ? 'rotate-180' : ''}`} />
        </button>

        {/* Mobile Selected Filters Chips */}
        {hasActiveFilters && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {selectedSubfield.map((sub) => (
              <span key={sub} className="inline-flex items-center gap-1 px-2 py-1 bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 text-xs rounded">
                {sub}
                <button onClick={() => onSubfieldChange(selectedSubfield.filter(s => s !== sub))}>
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
            {selectedCnkiSubject.map((sub) => (
              <span key={sub} className="inline-flex items-center gap-1 px-2 py-1 bg-teal-100 dark:bg-teal-900/40 text-teal-700 dark:text-teal-300 text-xs rounded">
                {sub}
                <button onClick={() => onCnkiSubjectChange(selectedCnkiSubject.filter(s => s !== sub))}>
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
            {selectedJournal.map((j) => (
              <span key={j} className="inline-flex items-center gap-1 px-2 py-1 bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 text-xs rounded">
                {j}
                <button onClick={() => onJournalChange(selectedJournal.filter(s => s !== j))}>
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
            {minScore && (
              <span className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-300 text-xs rounded">
                ≥ {(minScore * 100).toFixed(0)}%
                <button onClick={() => onMinScoreChange(null)}>
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            <button
              onClick={() => {
                onMinScoreChange(null);
                onSubfieldChange([]);
                onCnkiSubjectChange([]);
                onJournalChange([]);
              }}
              className="text-xs text-primary-600 dark:text-primary-400 hover:underline"
            >
              清除全部
            </button>
          </div>
        )}
      </div>

      {/* Desktop Filters */}
      <div className="hidden md:flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <MultiSelect
            options={subfields}
            selected={selectedSubfield}
            onChange={onSubfieldChange}
            label="子领域筛选"
            counts={stats ? (stats.subfield_counts as Record<string, number>) : {}}
          />

          <MultiSelect
            options={cnkiSubjects}
            selected={selectedCnkiSubject}
            onChange={onCnkiSubjectChange}
            label="专题筛选"
            counts={stats ? ((stats.cnki_subject_counts || {}) as Record<string, number>) : {}}
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
              className="border border-gray-300 dark:border-gray-600 rounded-md px-2.5 py-1.5 text-xs bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 outline-none focus:ring-1 focus:ring-primary-500"
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
              className="border border-gray-300 dark:border-gray-600 rounded-md px-2 py-1.5 text-xs bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 outline-none focus:ring-1 focus:ring-primary-500"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <button
              onClick={onSortOrderToggle}
              className="px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md text-xs bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-300"
            >
              {sortOrder === 'desc' ? '↓' : '↑'}
            </button>
          </div>

          <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300 cursor-pointer select-none">
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
                onSubfieldChange([]);
                onCnkiSubjectChange([]);
                onJournalChange([]);
              }}
              className="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 underline"
            >
              {t('filters.clearAll')}
            </button>
          )}
        </div>
      </div>

      {/* Mobile Filters Panel */}
      {mobileFiltersOpen && (
        <div className="md:hidden space-y-3 pt-3 border-t border-gray-200 dark:border-gray-700">
          <div className="grid grid-cols-1 gap-3">
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">子领域</label>
              <select
                value=""
                onChange={(e) => {
                  if (e.target.value) {
                    onSubfieldChange([...selectedSubfield, e.target.value]);
                    e.target.value = '';
                  }
                }}
                className="w-full border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              >
                <option value="">选择子领域...</option>
                {subfields.filter(s => !selectedSubfield.includes(s)).map((sub) => (
                  <option key={sub} value={sub}>{sub} ({stats?.subfield_counts?.[sub] || 0})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">专题</label>
              <select
                value=""
                onChange={(e) => {
                  if (e.target.value) {
                    onCnkiSubjectChange([...selectedCnkiSubject, e.target.value]);
                    e.target.value = '';
                  }
                }}
                className="w-full border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              >
                <option value="">选择专题...</option>
                {cnkiSubjects.filter(s => !selectedCnkiSubject.includes(s)).map((sub) => (
                  <option key={sub} value={sub}>{sub} ({stats?.cnki_subject_counts?.[sub] || 0})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">期刊</label>
              <select
                value=""
                onChange={(e) => {
                  if (e.target.value) {
                    onJournalChange([...selectedJournal, e.target.value]);
                    e.target.value = '';
                  }
                }}
                className="w-full border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              >
                <option value="">选择期刊...</option>
                {journals.filter(j => !selectedJournal.includes(j)).map((j) => (
                  <option key={j} value={j}>{j} ({stats?.journal_counts?.[j] || 0})</option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">最低评分</label>
                <select
                  value={minScore || ''}
                  onChange={(e) => onMinScoreChange(e.target.value ? parseFloat(e.target.value) : null)}
                  className="w-full border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                >
                  <option value="">不限</option>
                  {scoreThresholds.map((score) => (
                    <option key={score} value={score}>≥ {(score * 100).toFixed(0)}%</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">排序</label>
                <div className="flex gap-1">
                  <select
                    value={sortBy}
                    onChange={(e) => onSortByChange(e.target.value)}
                    className="flex-1 border border-gray-300 dark:border-gray-600 rounded-md px-2 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                  >
                    {SORT_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <button
                    onClick={onSortOrderToggle}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-700 text-gray-500 dark:text-gray-300"
                  >
                    {sortOrder === 'desc' ? '↓' : '↑'}
                  </button>
                </div>
              </div>
            </div>

            <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
              <input
                type="checkbox"
                checked={showBookmarksOnly}
                onChange={(e) => onBookmarksChange(e.target.checked)}
                className="rounded"
              />
              仅看收藏
            </label>
          </div>
        </div>
      )}
    </div>
  );
}