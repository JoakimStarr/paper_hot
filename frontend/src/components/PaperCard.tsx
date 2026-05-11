'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { PaperCard as PaperCardType } from '@/types/paper';
import { ExternalLink, Calendar, TrendingUp, Award, Bookmark } from 'lucide-react';
import { format } from 'date-fns';
import { useLanguage } from '@/contexts/LanguageContext';
import { getIssuePeriod, topicColors } from '@/lib/utils';
import { toggleBookmark, isBookmarked as checkBookmarked } from '@/lib/cache';

interface PaperCardProps {
  paper: PaperCardType;
}

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
  const router = useRouter();
  const score = paper.final_score;
  const isHighScore = score >= 0.7;
  const isTrending = paper.trend_score >= 0.6;
  const [bookmarked, setBookmarked] = useState(checkBookmarked(paper.id));

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md hover:shadow-lg transition-shadow duration-200 p-6 border border-gray-200 dark:border-gray-700">
      <div className="flex justify-between items-start mb-3">
        <div className="flex-1">
          <Link href={`/paper/${paper.id}`}>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white hover:text-primary-600 dark:hover:text-primary-400 cursor-pointer line-clamp-2">
              {paper.title}
            </h3>
          </Link>
        </div>
        <div className="flex items-center gap-2 ml-4">
          <button
            onClick={(e) => {
              e.preventDefault();
              const added = toggleBookmark(paper.id);
              setBookmarked(added);
            }}
            className="text-gray-400 dark:text-gray-500 hover:text-yellow-500 transition-colors"
            title={bookmarked ? '取消收藏' : '收藏'}
          >
            <Bookmark
              className={`w-4 h-4 ${bookmarked ? 'fill-yellow-500 text-yellow-500' : ''}`}
            />
          </button>
          {isHighScore && (
            <span className="flex items-center gap-1 bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-300 text-xs font-medium px-2 py-1 rounded">
              <Award className="w-3 h-3" />
              {t('paper.top')}
            </span>
          )}
          {isTrending && (
            <span className="flex items-center gap-1 bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-300 text-xs font-medium px-2 py-1 rounded">
              <TrendingUp className="w-3 h-3" />
              {t('paper.trending')}
            </span>
          )}
        </div>
      </div>

      {paper.abstract && (
        <p className="text-gray-600 dark:text-gray-400 text-sm mb-3 line-clamp-2">
          {paper.abstract}
        </p>
      )}

      {paper.authors && paper.authors.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 mb-3">
          <span className="text-xs text-gray-400 dark:text-gray-500 mr-1">作者:</span>
          {paper.authors.slice(0, 5).map((author, index) => (
            <button
              key={index}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                router.push(`/author/${encodeURIComponent(author.trim())}`);
              }}
              className="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-800 dark:hover:text-primary-300 hover:underline bg-primary-50 dark:bg-primary-900/30 hover:bg-primary-100 dark:hover:bg-primary-900/50 px-1.5 py-0.5 rounded transition-colors"
            >
              {author.trim()}
            </button>
          ))}
          {paper.authors.length > 5 && (
            <span className="text-xs text-gray-400 dark:text-gray-500">等{paper.authors.length}人</span>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-3">
        {paper.topic && (
          <span className={`text-xs font-medium px-2 py-1 rounded ${topicColors[paper.topic] || topicColors.Other}`}>
            {paper.topic}
          </span>
        )}
        {paper.economics_subfield && (
          <span className={`text-xs font-medium px-2 py-1 rounded ${subfieldColors[paper.economics_subfield] || 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'}`}>
            {paper.economics_subfield}
          </span>
        )}
        {paper.keywords_cn?.slice(0, 3).map((keyword, index) => (
          <button
            key={index}
            onClick={(e) => {
              e.preventDefault();
              router.push(`/search?search=${encodeURIComponent(keyword)}&search_field=keyword`);
            }}
            className="bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs px-2 py-1 rounded hover:bg-primary-100 dark:hover:bg-primary-900/50 hover:text-primary-700 dark:hover:text-primary-400 transition-colors cursor-pointer"
          >
            {keyword}
          </button>
        ))}
      </div>

      <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
        <div className="flex items-center gap-4 flex-wrap">
          <span className="flex items-center gap-1">
            <Calendar className="w-4 h-4" />
            {getIssuePeriod(paper.doi, paper.published_at, paper.journal_issue) || 'Unknown'}
          </span>
          <span className="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-xs">
            {paper.source}
          </span>
          {paper.venue && (
            <span className="bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400 px-2 py-1 rounded text-xs">
              {paper.venue}
            </span>
          )}
          {paper.journal_name && (
            <button
              onClick={() => router.push(`/search?journal=${encodeURIComponent(paper.journal_name!)}`)}
              className="bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 px-2 py-1 rounded text-xs hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors cursor-pointer"
            >
              {paper.journal_name}
            </button>
          )}
          {paper.journal_issue && (
            <span className="bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-2 py-1 rounded text-xs">
              {paper.journal_issue}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <div className="w-16 bg-gray-200 dark:bg-gray-600 rounded-full h-2">
              <div
                className="bg-primary-600 h-2 rounded-full"
                style={{ width: `${score * 100}%` }}
              />
            </div>
            <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
              {(score * 100).toFixed(0)}%
            </span>
          </div>
          <a
            href={paper.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      </div>
    </div>
  );
}
