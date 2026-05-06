'use client';

import React, { useState, useEffect } from 'react';
import Layout from '@/components/Layout';
import TrendChart from '@/components/TrendChart';
import { papersApi } from '@/lib/api';
import { TrendingTopic } from '@/types/paper';
import { Loader2 } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';

export default function TrendsPage() {
  const { t } = useLanguage();
  const [topics, setTopics] = useState<TrendingTopic[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTrends();
  }, []);

  const fetchTrends = async () => {
    setLoading(true);
    try {
      const response = await papersApi.getTrendingTopics(4);
      setTopics(response.topics);
    } catch (error) {
      console.error('Error fetching trends:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          {t('trends.title')}
        </h1>
        <p className="text-gray-600">
          {t('trends.subtitle')}
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      ) : (
        <TrendChart topics={topics} />
      )}
    </Layout>
  );
}
