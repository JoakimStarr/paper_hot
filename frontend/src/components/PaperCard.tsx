'use client';

import React from 'react';
import Link from 'next/link';
import { Paper } from '@/types/paper';
import { ExternalLink, Calendar, TrendingUp, Award } from 'lucide-react';
import { format } from 'date-fns';
import { useLanguage } from '@/contexts/LanguageContext';

interface PaperCardProps {
  paper: Paper;
}

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

const subfieldColors: Record<string, string> = {
  '宏观经济学': 'bg-blue-100 text-blue-800',
  '微观经济学': 'bg-green-100 text-green-800',
  '计量经济学': 'bg-purple-100 text-purple-800',
  '金融经济学': 'bg-yellow-100 text-yellow-800',
  '产业经济学': 'bg-red-100 text-red-800',
  '发展经济学': 'bg-indigo-100 text-indigo-800',
  '国际经济学': 'bg-pink-100 text-pink-800',
};

export default function PaperCard({ paper }: PaperCardProps) {
  const { t } = useLanguage();
  const score = paper.scores?.final_score || 0;
  const isHighScore = score >= 0.7;
  const isTrending = paper.scores?.trend_score && paper.scores.trend_score >= 0.6;

  return (
    <div className="bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow duration-200 p-6 border border-gray-200">
      <div className="flex justify-between items-start mb-3">
        <div className="flex-1">
          <Link href={`/paper/${paper.id}`}>
            <h3 className="text-lg font-semibold text-gray-900 hover:text-primary-600 cursor-pointer line-clamp-2">
              {paper.title}
            </h3>
          </Link>
        </div>
        <div className="flex items-center gap-2 ml-4">
          {isHighScore && (
            <span className="flex items-center gap-1 bg-yellow-100 text-yellow-800 text-xs font-medium px-2 py-1 rounded">
              <Award className="w-3 h-3" />
              {t('paper.top')}
            </span>
          )}
          {isTrending && (
            <span className="flex items-center gap-1 bg-red-100 text-red-800 text-xs font-medium px-2 py-1 rounded">
              <TrendingUp className="w-3 h-3" />
              {t('paper.trending')}
            </span>
          )}
        </div>
      </div>

      {paper.features?.summary && (
        <p className="text-gray-600 text-sm mb-3 line-clamp-2">
          {paper.features.summary}
        </p>
      )}

      <div className="flex flex-wrap gap-2 mb-3">
        {paper.features?.topic && (
          <span className={`text-xs font-medium px-2 py-1 rounded ${topicColors[paper.features.topic] || topicColors.Other}`}>
            {paper.features.topic}
          </span>
        )}
        {paper.economics_subfield && (
          <span className={`text-xs font-medium px-2 py-1 rounded ${subfieldColors[paper.economics_subfield] || 'bg-gray-100 text-gray-800'}`}>
            {paper.economics_subfield}
          </span>
        )}
        {paper.features?.keywords?.slice(0, 3).map((keyword, index) => (
          <span key={index} className="bg-gray-100 text-gray-700 text-xs px-2 py-1 rounded">
            {keyword}
          </span>
        ))}
      </div>

      <div className="flex items-center justify-between text-sm text-gray-500">
        <div className="flex items-center gap-4 flex-wrap">
          <span className="flex items-center gap-1">
            <Calendar className="w-4 h-4" />
            {paper.published_at ? format(new Date(paper.published_at), 'MMM d, yyyy') : 'Unknown'}
          </span>
          <span className="bg-gray-100 px-2 py-1 rounded text-xs">
            {paper.source}
          </span>
          {paper.venue && (
            <span className="bg-primary-50 text-primary-700 px-2 py-1 rounded text-xs">
              {paper.venue}
            </span>
          )}
          {paper.journal_name && (
            <span className="bg-blue-50 text-blue-700 px-2 py-1 rounded text-xs">
              {paper.journal_name}
            </span>
          )}
          {paper.journal_issue && (
            <span className="bg-gray-50 text-gray-700 px-2 py-1 rounded text-xs">
              {paper.journal_issue}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <div className="w-16 bg-gray-200 rounded-full h-2">
              <div
                className="bg-primary-600 h-2 rounded-full"
                style={{ width: `${score * 100}%` }}
              />
            </div>
            <span className="text-xs font-medium text-gray-700">
              {(score * 100).toFixed(0)}%
            </span>
          </div>
          <a
            href={paper.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary-600 hover:text-primary-700"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      </div>
    </div>
  );
}
