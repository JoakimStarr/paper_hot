'use client';

import React from 'react';
import Layout from '@/components/Layout';
import { Settings, Activity } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';

export default function SystemPage() {
  const { t } = useLanguage();

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          {t('system.title')}
        </h1>
        <p className="text-gray-600">
          {t('system.subtitle')}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <Settings className="w-6 h-6 text-primary-600" />
            <h2 className="text-xl font-semibold text-gray-900">{t('system.crawlControl')}</h2>
          </div>
          <div className="text-gray-500 text-center py-12 border-2 border-dashed border-gray-300 rounded-lg">
            {t('system.crawlControl')} ({t('system.crawling')})
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <Activity className="w-6 h-6 text-primary-600" />
            <h2 className="text-xl font-semibold text-gray-900">{t('system.crawlLogs')}</h2>
          </div>
          <div className="text-gray-500 text-center py-12 border-2 border-dashed border-gray-300 rounded-lg">
            {t('system.crawlLogs')} ({t('system.crawling')})
          </div>
        </div>
      </div>
    </Layout>
  );
}
