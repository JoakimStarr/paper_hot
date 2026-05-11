'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Search, X } from 'lucide-react';
import { papersApi, SearchSuggestion } from '@/lib/api';
import { useRouter } from 'next/navigation';

interface SearchBarProps {
  initialQuery?: string;
  initialField?: string;
  onSearch: (query: string, field: string) => void;
}

const SEARCH_FIELDS = [
  { value: 'keyword', label: '关键词' },
  { value: 'title', label: '标题' },
  { value: 'author', label: '作者' },
  { value: 'all', label: '全部' },
];

export default function SearchBar({ initialQuery = '', initialField = 'keyword', onSearch }: SearchBarProps) {
  const [query, setQuery] = useState(initialQuery);
  const [field, setField] = useState(initialField);
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const suggestRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const router = useRouter();

  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  useEffect(() => {
    setField(initialField);
  }, [initialField]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (suggestRef.current && !suggestRef.current.contains(e.target as Node) &&
          inputRef.current && !inputRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const fetchSuggestions = useCallback(async (q: string) => {
    if (q.trim().length < 1) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    try {
      const result = await papersApi.getSearchSuggestions(q.trim());
      setSuggestions(result.suggestions);
      setShowSuggestions(result.suggestions.length > 0);
      setHighlightIndex(-1);
    } catch {
      setSuggestions([]);
    }
  }, []);

  const handleInputChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchSuggestions(value);
    }, 250);
  };

  const handleSubmit = (searchQuery?: string) => {
    const trimmed = (searchQuery || query).trim();
    if (!trimmed) return;
    setShowSuggestions(false);
    onSearch(trimmed, field);
  };

  const handleSuggestionClick = (suggestion: SearchSuggestion) => {
    setQuery(suggestion.text);
    setShowSuggestions(false);
    if (suggestion.type === 'title') {
      router.push(`/search?search=${encodeURIComponent(suggestion.text)}&search_field=title`);
    } else if (suggestion.type === 'author') {
      router.push(`/search?search=${encodeURIComponent(suggestion.text)}&search_field=author`);
    } else {
      onSearch(suggestion.text, 'keyword');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      if (showSuggestions && highlightIndex >= 0 && highlightIndex < suggestions.length) {
        handleSuggestionClick(suggestions[highlightIndex]);
      } else {
        handleSubmit();
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightIndex(prev =>
        prev < suggestions.length - 1 ? prev + 1 : 0
      );
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIndex(prev =>
        prev > 0 ? prev - 1 : suggestions.length - 1
      );
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
      setHighlightIndex(-1);
    }
  };

  const handleClear = () => {
    setQuery('');
    setSuggestions([]);
    setShowSuggestions(false);
    inputRef.current?.focus();
  };

  return (
    <div className="relative">
      <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2 border border-gray-200">
        <Search className="w-4 h-4 text-gray-400 shrink-0" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => handleInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (suggestions.length > 0) setShowSuggestions(true);
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
          onClick={() => handleSubmit()}
          className="bg-primary-600 text-white rounded px-3 py-1 text-sm hover:bg-primary-700 shrink-0"
        >
          搜索
        </button>
      </div>

      {showSuggestions && suggestions.length > 0 && (
        <div ref={suggestRef} className="absolute z-50 left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg overflow-hidden">
          {suggestions.map((suggestion, index) => (
            <button
              key={`${suggestion.type}-${suggestion.text}-${index}`}
              onMouseDown={(e) => {
                e.preventDefault();
                handleSuggestionClick(suggestion);
              }}
              onMouseEnter={() => setHighlightIndex(index)}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left hover:bg-gray-50 transition-colors ${index === highlightIndex ? 'bg-gray-50' : ''}`}
            >
              <span className={`shrink-0 px-1.5 py-0.5 rounded text-xs font-medium ${
                suggestion.type === 'keyword'
                  ? 'bg-green-100 text-green-700'
                  : suggestion.type === 'author'
                  ? 'bg-orange-100 text-orange-700'
                  : 'bg-blue-100 text-blue-700'
              }`}>
                {suggestion.type === 'keyword' ? '关键词' : suggestion.type === 'author' ? '作者' : '标题'}
              </span>
              <span className="text-gray-700 truncate flex-1">{suggestion.text}</span>
              {suggestion.count > 0 && (
                <span className="text-xs text-gray-400 shrink-0">{suggestion.count}篇</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}