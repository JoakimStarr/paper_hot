'use client';

import React, { useState } from 'react';
import { Search, X } from 'lucide-react';

interface SearchBarProps {
  initialQuery?: string;
  initialField?: string;
  onSearch: (query: string, field: string) => void;
}

const SEARCH_FIELDS = [
  { value: 'keyword', label: '关键词' },
  { value: 'title', label: '标题' },
  { value: 'all', label: '全部' },
];

export default function SearchBar({ initialQuery = '', initialField = 'keyword', onSearch }: SearchBarProps) {
  const [query, setQuery] = useState(initialQuery);
  const [field, setField] = useState(initialField);

  const handleSubmit = () => {
    const trimmed = query.trim();
    if (!trimmed) return;
    onSearch(trimmed, field);
  };

  const handleClear = () => {
    setQuery('');
  };

  return (
    <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2 border border-gray-200">
      <Search className="w-4 h-4 text-gray-400 shrink-0" />
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSubmit();
        }}
        placeholder="搜索论文关键词、标题..."
        className="flex-1 bg-transparent text-sm outline-none"
      />
      <select
        value={field}
        onChange={(e) => setField(e.target.value)}
        className="text-xs bg-white border border-gray-200 rounded px-2 py-0.5 shrink-0 outline-none"
      >
        {SEARCH_FIELDS.map((f) => (
          <option key={f.value} value={f.value}>{f.label}</option>
        ))}
      </select>
      {query && (
        <button onClick={handleClear} className="p-0.5 hover:bg-gray-200 rounded">
          <X className="w-3 h-3 text-gray-400" />
        </button>
      )}
      <button
        onClick={handleSubmit}
        className="bg-primary-600 text-white rounded px-3 py-1 text-sm hover:bg-primary-700 shrink-0"
      >
        搜索
      </button>
    </div>
  );
}