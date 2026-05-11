import React, { useState, useEffect, useRef, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { FileText, TrendingUp, Home, Settings, Share2, Search, Wifi, WifiOff, Sun, Moon, X } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { useTheme } from '@/contexts/ThemeContext';
import { papersApi, SearchSuggestion } from '@/lib/api';
import LanguageSwitcher from './LanguageSwitcher';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const { t } = useLanguage();
  const { isDark, toggleDark } = useTheme();
  const router = useRouter();
  const [backendOnline, setBackendOnline] = useState(true);

  const [showSearch, setShowSearch] = useState(false);
  const [navQuery, setNavQuery] = useState('');
  const [navSuggestions, setNavSuggestions] = useState<SearchSuggestion[]>([]);
  const [showNavSuggestions, setShowNavSuggestions] = useState(false);
  const navSearchRef = useRef<HTMLDivElement>(null);
  const navInputRef = useRef<HTMLInputElement>(null);
  const navDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (showSearch && navInputRef.current) {
      navInputRef.current.focus();
    }
  }, [showSearch]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (navSearchRef.current && !navSearchRef.current.contains(e.target as Node)) {
        setShowNavSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleNavSearch = useCallback((q?: string) => {
    const trimmed = (q || navQuery).trim();
    if (!trimmed) return;
    setShowNavSuggestions(false);
    setNavQuery('');
    setShowSearch(false);
    router.push(`/search?search=${encodeURIComponent(trimmed)}&search_field=keyword`);
  }, [navQuery, router]);

  const handleNavInputChange = useCallback((value: string) => {
    setNavQuery(value);
    if (navDebounceRef.current) clearTimeout(navDebounceRef.current);
    if (value.trim().length < 1) {
      setNavSuggestions([]);
      setShowNavSuggestions(false);
      return;
    }
    navDebounceRef.current = setTimeout(async () => {
      try {
        const result = await papersApi.getSearchSuggestions(value.trim());
        setNavSuggestions(result.suggestions);
        setShowNavSuggestions(result.suggestions.length > 0);
      } catch {
        setNavSuggestions([]);
      }
    }, 300);
  }, []);

  useEffect(() => {
    const checkBackend = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/health`, { signal: AbortSignal.timeout(5000) });
        setBackendOnline(res.ok);
      } catch {
        setBackendOnline(false);
      }
    };
    checkBackend();
    const interval = setInterval(checkBackend, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-300">
      <header className="bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700 transition-colors duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link href="/" className="flex items-center gap-2 shrink-0">
              <FileText className="w-8 h-8 text-primary-600 dark:text-primary-400" />
              <span className="text-xl font-bold text-gray-900 dark:text-white">{t('appName')}</span>
            </Link>
            
            <nav className="flex items-center gap-3">
              <Link
                href="/"
                className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors text-sm"
              >
                <Home className="w-4 h-4" />
                <span className="hidden sm:inline">{t('nav.home')}</span>
              </Link>

              {showSearch ? (
                <div ref={navSearchRef} className="relative">
                  <div className="flex items-center bg-gray-100 dark:bg-gray-700 rounded-full px-3 py-1.5 gap-1.5">
                    <Search className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                    <input
                      ref={navInputRef}
                      type="text"
                      value={navQuery}
                      onChange={(e) => handleNavInputChange(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') handleNavSearch(); if (e.key === 'Escape') { setShowSearch(false); setNavQuery(''); setNavSuggestions([]); } }}
                      onFocus={() => { if (navSuggestions.length > 0) setShowNavSuggestions(true); }}
                      placeholder="搜索..."
                      className="bg-transparent text-sm outline-none w-28 sm:w-40 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                    />
                    <button onClick={() => { setShowSearch(false); setNavQuery(''); setNavSuggestions([]); }} className="p-0.5 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-full transition-colors">
                      <X className="w-3 h-3 text-gray-400" />
                    </button>
                  </div>
                  {showNavSuggestions && navSuggestions.length > 0 && (
                    <div className="absolute right-0 top-full mt-1 w-64 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 overflow-hidden">
                      {navSuggestions.slice(0, 5).map((s, i) => (
                        <button
                          key={`${s.type}-${s.text}-${i}`}
                          onMouseDown={(e) => {
                            e.preventDefault();
                            setShowNavSuggestions(false);
                            setNavQuery('');
                            setShowSearch(false);
                            const field = s.type === 'author' ? 'author' : s.type === 'title' ? 'title' : 'keyword';
                            router.push(`/search?search=${encodeURIComponent(s.text)}&search_field=${field}`);
                          }}
                          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-gray-700 dark:text-gray-300"
                        >
                          <span className={`shrink-0 px-1.5 py-0.5 rounded text-xs font-medium ${
                            s.type === 'keyword' ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400'
                              : s.type === 'author' ? 'bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-400'
                              : 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400'
                          }`}>
                            {s.type === 'keyword' ? '关键词' : s.type === 'author' ? '作者' : '标题'}
                          </span>
                          <span className="truncate flex-1">{s.text}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <button
                  onClick={() => setShowSearch(true)}
                  className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors text-sm"
                >
                  <Search className="w-4 h-4" />
                  <span className="hidden sm:inline">搜索</span>
                </button>
              )}

              <Link
                href="/trends"
                className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors text-sm"
              >
                <TrendingUp className="w-4 h-4" />
                <span className="hidden sm:inline">{t('nav.trends')}</span>
              </Link>
              <Link
                href="/network"
                className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors text-sm"
              >
                <Share2 className="w-4 h-4" />
                <span className="hidden sm:inline">关系网络</span>
              </Link>
              <Link
                href="/system"
                className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors text-sm"
              >
                <Settings className="w-4 h-4" />
                <span className="hidden sm:inline">{t('nav.system')}</span>
              </Link>
              <LanguageSwitcher />
              <button
                onClick={toggleDark}
                className="p-1.5 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors duration-300"
                title={isDark ? '切换亮色模式' : '切换暗色模式'}
              >
                {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              </button>
              <div className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-full transition-colors duration-300 ${backendOnline ? 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-900/30' : 'text-red-500 bg-red-50 dark:text-red-400 dark:bg-red-900/30'}`}>
                {backendOnline ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
                <span className="hidden sm:inline">{backendOnline ? '在线' : '离线'}</span>
              </div>
            </nav>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>

      <footer className="bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 mt-12 transition-colors duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="text-center text-gray-600 dark:text-gray-400 text-sm">
            <p>{t('appName')} - {t('footer.description')}</p>
            <p className="mt-1">{t('footer.builtWith')}</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
