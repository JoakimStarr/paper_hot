import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { FileText, TrendingUp, Home, Settings, Share2, Search, Wifi, WifiOff, Sun, Moon } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { useTheme } from '@/contexts/ThemeContext';
import LanguageSwitcher from './LanguageSwitcher';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const { t } = useLanguage();
  const { isDark, toggleDark } = useTheme();
  const [backendOnline, setBackendOnline] = useState(true);

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
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 transition-colors">
      <header className="bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700 transition-colors">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link href="/" className="flex items-center gap-2">
              <FileText className="w-8 h-8 text-primary-600 dark:text-primary-400" />
              <span className="text-xl font-bold text-gray-900 dark:text-white">{t('appName')}</span>
            </Link>
            
            <nav className="flex items-center gap-6">
              <Link
                href="/"
                className="flex items-center gap-2 text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
              >
                <Home className="w-5 h-5" />
                <span>{t('nav.home')}</span>
              </Link>
              <Link
                href="/search"
                className="flex items-center gap-2 text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
              >
                <Search className="w-5 h-5" />
                <span>搜索</span>
              </Link>
              <Link
                href="/trends"
                className="flex items-center gap-2 text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
              >
                <TrendingUp className="w-5 h-5" />
                <span>{t('nav.trends')}</span>
              </Link>
              <Link
                href="/network"
                className="flex items-center gap-2 text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
              >
                <Share2 className="w-5 h-5" />
                <span>关系网络</span>
              </Link>
              <Link
                href="/system"
                className="flex items-center gap-2 text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
              >
                <Settings className="w-5 h-5" />
                <span>{t('nav.system')}</span>
              </Link>
              <LanguageSwitcher />
              <button
                onClick={toggleDark}
                className="p-1.5 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                title={isDark ? '切换亮色模式' : '切换暗色模式'}
              >
                {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              </button>
              <div className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-full ${backendOnline ? 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-900/30' : 'text-red-500 bg-red-50 dark:text-red-400 dark:bg-red-900/30'}`}>
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

      <footer className="bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 mt-12 transition-colors">
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
