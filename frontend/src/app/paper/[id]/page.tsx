'use client';

import React, { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Layout from '@/components/Layout';
import { papersApi } from '@/lib/api';
import { PaperDetailResponse } from '@/types/paper';
import { Loader2, ExternalLink, Calendar, Award, TrendingUp, ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { format } from 'date-fns';
import { useLanguage } from '@/contexts/LanguageContext';

const topicColors: Record<string, string> = {
  LLM: 'bg-purple-100 text-purple-800',
  Agent: 'bg-green-100 text-green-800',
  CV: 'bg-blue-100 text-blue-800',
  RL: 'bg-orange-100 text-orange-800',
  Multimodal: 'bg-pink-100 text-pink-800',
  NLP: 'bg-yellow-100 text-yellow-800',
  Generative: 'bg-indigo-100 text-indigo-800',
  Other: 'bg-gray-100 text-gray-800',
};

export default function PaperDetailPage() {
  const { t } = useLanguage();
  const params = useParams();
  const [paper, setPaper] = useState<PaperDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (params.id) {
      fetchPaper();
    }
  }, [params.id]);

  const fetchPaper = async () => {
    setLoading(true);
    try {
      const response = await papersApi.getPaperById(params.id as string);
      setPaper(response);
    } catch (error) {
      console.error('Error fetching paper:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      </Layout>
    );
  }

  if (!paper) {
    return (
      <Layout>
        <div className="text-center py-12">
          <p className="text-gray-600">{t('home.noPapers')}</p>
          <Link href="/" className="text-primary-600 hover:underline mt-4 inline-block">
            {t('nav.home')}
          </Link>
        </div>
      </Layout>
    );
  }

  const score = paper.scores?.final_score || 0;
  const shouldReadScore = paper.should_read_score || score;

  return (
    <Layout>
      <div className="mb-6">
        <Link href="/" className="flex items-center gap-2 text-gray-600 hover:text-primary-600 transition-colors">
          <ArrowLeft className="w-5 h-5" />
          <span>{t('home.previous')}</span>
        </Link>
      </div>

      <div className="bg-white rounded-lg shadow-md p-8 mb-6">
        <div className="flex justify-between items-start mb-4">
          <h1 className="text-2xl font-bold text-gray-900 flex-1">
            {paper.title}
          </h1>
          <a
            href={paper.url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-4 text-primary-600 hover:text-primary-700"
          >
            <ExternalLink className="w-6 h-6" />
          </a>
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          {paper.features?.topic && (
            <span className={`text-sm font-medium px-3 py-1 rounded ${topicColors[paper.features.topic] || topicColors.Other}`}>
              {paper.features.topic}
            </span>
          )}
          {paper.features?.keywords?.map((keyword, index) => (
            <span key={index} className="bg-gray-100 text-gray-700 text-sm px-3 py-1 rounded">
              {keyword}
            </span>
          ))}
        </div>

        <div className="flex items-center gap-6 text-sm text-gray-600 mb-6">
          <span className="flex items-center gap-1">
            <Calendar className="w-4 h-4" />
            {paper.published_at ? format(new Date(paper.published_at), 'MMMM d, yyyy') : 'Unknown date'}
          </span>
          <span className="bg-gray-100 px-3 py-1 rounded">
            {paper.source}
          </span>
          {paper.venue && (
            <span className="bg-primary-50 text-primary-700 px-3 py-1 rounded">
              {paper.venue}
            </span>
          )}
        </div>

        <div className="mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">{t('paper.authors')}</h2>
          <p className="text-gray-700">{paper.authors.join(', ')}</p>
        </div>

        {paper.features?.keywords && paper.features.keywords.length > 0 && (
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-2">{t('paper.keywords')}</h2>
            <div className="flex flex-wrap gap-2">
              {paper.features.keywords.map((keyword, index) => (
                <span key={index} className="bg-primary-100 text-primary-800 text-sm px-3 py-1 rounded-full">
                  {keyword}
                </span>
              ))}
            </div>
          </div>
        )}

        {paper.features?.summary && (
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-2">{t('paper.abstract')}</h2>
            <p className="text-gray-700 bg-blue-50 p-4 rounded-lg">
              {paper.features.summary}
            </p>
          </div>
        )}

        <div className="border-t border-gray-200 pt-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('paper.score')}</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Overall Score</div>
              <div className="flex items-center gap-2">
                <div className="flex-1 bg-gray-200 rounded-full h-3">
                  <div
                    className="bg-primary-600 h-3 rounded-full"
                    style={{ width: `${score * 100}%` }}
                  />
                </div>
                <span className="text-lg font-bold text-gray-900">
                  {(score * 100).toFixed(0)}%
                </span>
              </div>
            </div>

            <div className="bg-gray-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Recency</div>
              <div className="text-lg font-bold text-gray-900">
                {((paper.scores?.recency_score || 0) * 100).toFixed(0)}%
              </div>
            </div>

            <div className="bg-gray-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Venue Quality</div>
              <div className="text-lg font-bold text-gray-900">
                {((paper.scores?.venue_score || 0) * 100).toFixed(0)}%
              </div>
            </div>

            <div className="bg-gray-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Trend Score</div>
              <div className="text-lg font-bold text-gray-900">
                {((paper.scores?.trend_score || 0) * 100).toFixed(0)}%
              </div>
            </div>
          </div>

          {paper.should_read_score && (
            <div className="mt-4 bg-yellow-50 border border-yellow-200 p-4 rounded-lg">
              <div className="flex items-center gap-2">
                <Award className="w-5 h-5 text-yellow-700" />
                <span className="font-semibold text-yellow-900">
                  {t('paper.shouldReadScore')}: {(shouldReadScore * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-sm text-yellow-800 mt-1">
                {shouldReadScore >= 0.7
                  ? t('paper.highlyRecommended')
                  : shouldReadScore >= 0.5
                  ? t('paper.worthReading')
                  : t('paper.considerReading')}
              </p>
            </div>
          )}
        </div>
      </div>

      {paper.similar_papers && paper.similar_papers.length > 0 && (
        <div className="bg-white rounded-lg shadow-md p-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">{t('paper.similarPapers')}</h2>
          <div className="space-y-3">
            {paper.similar_papers.map((similar) => (
              <Link
                key={similar.id}
                href={`/paper/${similar.id}`}
                className="block border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <h3 className="font-semibold text-gray-900 mb-1">
                      {similar.title}
                    </h3>
                    {similar.topic && (
                      <span className={`text-xs font-medium px-2 py-1 rounded ${topicColors[similar.topic] || topicColors.Other}`}>
                        {similar.topic}
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-600">
                    {(similar.similarity_score * 100).toFixed(0)}% similar
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </Layout>
  );
}
