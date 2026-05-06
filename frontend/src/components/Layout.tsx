import React from 'react';
import Link from 'next/link';
import { FileText, TrendingUp, Home, Settings } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import LanguageSwitcher from './LanguageSwitcher';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const { t } = useLanguage();

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link href="/" className="flex items-center gap-2">
              <FileText className="w-8 h-8 text-primary-600" />
              <span className="text-xl font-bold text-gray-900">{t('appName')}</span>
            </Link>
            
            <nav className="flex items-center gap-6">
              <Link
                href="/"
                className="flex items-center gap-2 text-gray-600 hover:text-primary-600 transition-colors"
              >
                <Home className="w-5 h-5" />
                <span>{t('nav.home')}</span>
              </Link>
              <Link
                href="/trends"
                className="flex items-center gap-2 text-gray-600 hover:text-primary-600 transition-colors"
              >
                <TrendingUp className="w-5 h-5" />
                <span>{t('nav.trends')}</span>
              </Link>
              <Link
                href="/system"
                className="flex items-center gap-2 text-gray-600 hover:text-primary-600 transition-colors"
              >
                <Settings className="w-5 h-5" />
                <span>{t('nav.system')}</span>
              </Link>
              <LanguageSwitcher />
            </nav>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>

      <footer className="bg-white border-t border-gray-200 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="text-center text-gray-600 text-sm">
            <p>{t('appName')} - {t('footer.description')}</p>
            <p className="mt-1">{t('footer.builtWith')}</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
