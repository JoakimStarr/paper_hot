import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { FileText, TrendingUp, Home, Settings, Share2, WifiOff, Sun, Moon, Menu, Compass, LayoutDashboard, History } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { useTheme } from '@/contexts/ThemeContext';
import { initBookmarks, initPins } from '@/lib/cache';
import ToastProvider from '@/components/Toast';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const { t } = useLanguage();
  const { isDark, toggleDark } = useTheme();
  const pathname = usePathname();
  const [backendOnline, setBackendOnline] = useState(true);
  // 手动重试计数：离线警告条点「重试」时 +1，触发健康探测重跑
  const [healthRetry, setHealthRetry] = useState(0);

  // 桌面端导航高亮
  const navLinkClass = (path: string) => {
    const active = path === '/' ? pathname === '/' : pathname.startsWith(path);
    return `flex items-center gap-1.5 transition-colors text-sm ${
      active
        ? 'text-primary-600 dark:text-primary-400 font-medium'
        : 'text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400'
    }`;
  };
  // 移动端菜单高亮：加大点按区域并带背景色标出当前页
  const mobileLinkClass = (path: string) => {
    const active = path === '/' ? pathname === '/' : pathname.startsWith(path);
    return `flex items-center gap-3 px-3 py-2.5 text-sm rounded-md transition-colors ${
      active
        ? 'text-primary-600 dark:text-primary-400 font-medium bg-primary-50 dark:text-primary-300 dark:bg-gray-700/40'
        : 'text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 hover:bg-gray-50 dark:hover:bg-gray-700'
    }`;
  };
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const mobileMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (mobileMenuRef.current && !mobileMenuRef.current.contains(e.target as Node)) {
        setMobileMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    // 启动即拉取服务端收藏（P1-10）与手动置顶（P2），并迁移旧 localStorage 数据
    initBookmarks().catch(() => {});
    initPins().catch(() => {});

    let cancelled = false;
    const checkBackend = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || '/api';
        const baseUrl = apiUrl.replace(/\/api$/, '');
        const res = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(5000) });
        if (!cancelled) setBackendOnline(res.ok);
      } catch {
        if (!cancelled) setBackendOnline(false);
      }
    };
    checkBackend();
    // 60s 低频探测：仅在离线时展示警告条，正常时不打扰
    const interval = setInterval(checkBackend, 60000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [healthRetry]);

  // 手动重试：离线警告条点击后立即重新探测
  const retryHealth = () => setHealthRetry(healthRetry + 1);

  return (
    <ToastProvider>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-300">
      <header className="sticky top-0 z-40 bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700 transition-colors duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link href="/" className="flex items-center gap-2 shrink-0">
              <FileText className="w-7 h-7 sm:w-8 sm:h-8 text-primary-600 dark:text-primary-400" />
              <span className="text-lg sm:text-xl font-bold text-gray-900 dark:text-white">{t('appName')}</span>
            </Link>
            
            {/* Desktop Navigation */}
            <nav className="hidden md:flex items-center gap-3">
              <Link href="/" className={navLinkClass('/')}>
                <Home className="w-4 h-4" />
                <span>{t('nav.home')}</span>
              </Link>
              <Link href="/dashboard" className={navLinkClass('/dashboard')}>
                <LayoutDashboard className="w-4 h-4" />
                <span>{t('nav.dashboard')}</span>
              </Link>

              <Link href="/reading" className={navLinkClass('/reading')}>
                <History className="w-4 h-4" />
                <span>{t('nav.reading')}</span>
              </Link>

              <Link href="/trends" className={navLinkClass('/trends')}>
                <TrendingUp className="w-4 h-4" />
                <span>{t('nav.trends')}</span>
              </Link>
              <Link href="/topics" className={navLinkClass('/topics')}>
                <Compass className="w-4 h-4" />
                <span>{t('nav.topics')}</span>
              </Link>
              <Link href="/network" className={navLinkClass('/network')}>
                <Share2 className="w-4 h-4" />
                <span>{t('nav.network')}</span>
              </Link>
              <Link href="/system" className={navLinkClass('/system')}>
                <Settings className="w-4 h-4" />
                <span>{t('nav.system')}</span>
              </Link>
              <button
                onClick={toggleDark}
                className="p-1.5 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors duration-300"
                title={isDark ? t('common.toggleLight') : t('common.toggleDark')}
              >
                {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              </button>
            </nav>

            {/* Mobile Navigation */}
            <div className="flex md:hidden items-center gap-2">
              <button
                onClick={toggleDark}
                aria-label={isDark ? t('common.toggleLight') : t('common.toggleDark')}
                className="p-2 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors duration-300"
              >
                {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
              </button>
              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                aria-label={t('common.menu')}
                aria-expanded={mobileMenuOpen}
                className="p-2 text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
              >
                <Menu className="w-6 h-6" />
              </button>
            </div>
          </div>
        </div>

        {/* Mobile Menu */}
        {mobileMenuOpen && (
          <div ref={mobileMenuRef} className="pp-menu-in md:hidden border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg">
            <nav className="px-3 py-3 space-y-1">
              <Link
                href="/"
                onClick={() => setMobileMenuOpen(false)}
                className={mobileLinkClass('/')}
              >
                <Home className="w-5 h-5" />
                <span>{t('nav.home')}</span>
              </Link>
              <Link
                href="/dashboard"
                onClick={() => setMobileMenuOpen(false)}
                className={mobileLinkClass('/dashboard')}
              >
                <LayoutDashboard className="w-5 h-5" />
                <span>{t('nav.dashboard')}</span>
              </Link>
              <Link
                href="/reading"
                onClick={() => setMobileMenuOpen(false)}
                className={mobileLinkClass('/reading')}
              >
                <History className="w-5 h-5" />
                <span>{t('nav.reading')}</span>
              </Link>
              <Link
                href="/trends"
                onClick={() => setMobileMenuOpen(false)}
                className={mobileLinkClass('/trends')}
              >
                <TrendingUp className="w-5 h-5" />
                <span>{t('nav.trends')}</span>
              </Link>
              <Link
                href="/topics"
                onClick={() => setMobileMenuOpen(false)}
                className={mobileLinkClass('/topics')}
              >
                <Compass className="w-5 h-5" />
                <span>{t('nav.topics')}</span>
              </Link>
              <Link
                href="/network"
                onClick={() => setMobileMenuOpen(false)}
                className={mobileLinkClass('/network')}
              >
                <Share2 className="w-5 h-5" />
                <span>{t('nav.network')}</span>
              </Link>
              <Link
                href="/system"
                onClick={() => setMobileMenuOpen(false)}
                className={mobileLinkClass('/system')}
              >
                <Settings className="w-5 h-5" />
                <span>{t('nav.system')}</span>
              </Link>
              <div className="border-t border-gray-200 dark:border-gray-700 pt-3 mt-3 px-3">
                {/* 在线状态已移除：仅在后端离线时于页面顶部展示警告条 */}
              </div>
            </nav>
            <style jsx>{`
              @keyframes ppMenuIn {
                from { opacity: 0; transform: translateY(-6px); }
                to { opacity: 1; transform: translateY(0); }
              }
              .pp-menu-in { animation: ppMenuIn .18s ease; }
            `}</style>
          </div>
        )}
        </header>

      {/* 后端离线警告条：正常时不显示，只有在健康探测失败时出现 */}
      {!backendOnline && (
        <div className="bg-amber-50 dark:bg-amber-900/30 border-b border-amber-200 dark:border-amber-800">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2 flex items-center gap-2 text-sm text-amber-700 dark:text-amber-300">
            <WifiOff className="w-4 h-4 shrink-0" />
            <span className="flex-1">{t('common.backendOffline')}</span>
            <button
              onClick={retryHealth}
              className="text-xs font-medium underline underline-offset-2 hover:text-amber-900 dark:hover:text-amber-100 transition-colors"
            >
              {t('common.retry')}
            </button>
          </div>
        </div>
      )}

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
    </ToastProvider>
  );
}
