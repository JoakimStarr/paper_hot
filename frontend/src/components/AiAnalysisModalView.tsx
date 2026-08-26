'use client';

/**
 * AiAnalysisModalView —— 重展示层（PERF_PLAN 1.1 P0）。
 * 模态 UI + MarkdownRenderer（react-markdown 全家桶）隔离在本 chunk，
 * 仅在弹窗打开时经 next/dynamic 挂载，不进入共享 layout chunk。
 */
import React from 'react';
import { Sparkles, X, Loader2 } from 'lucide-react';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import { useLanguage } from '@/contexts/LanguageContext';

interface ViewProps {
  paperTitle: string;
  loading: boolean;
  content: string | null;
  error: boolean;
  needsStart: boolean;
  onClose: () => void;
  onStart: () => void;
}

export default function AiAnalysisModalView({
  paperTitle, loading, content, error, needsStart, onClose, onStart,
}: ViewProps) {
  const { t } = useLanguage();

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div className="pointer-events-auto w-full max-w-2xl max-h-[80vh] flex flex-col bg-white dark:bg-gray-800 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-700 shrink-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-gray-100 min-w-0">
              <Sparkles className="w-4 h-4 text-purple-500 shrink-0" />
              {paperTitle ? (
                <span className="truncate">{paperTitle}</span>
              ) : (
                <span>{t('paper.aiAnalyze')}</span>
              )}
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors p-1 shrink-0"
              title={t('paper.aiClose')}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4 text-sm text-gray-700 dark:text-gray-300">
            {loading ? (
              <div className="flex flex-col items-center justify-center py-14 gap-3">
                <Loader2 className="w-6 h-6 animate-spin text-purple-500" />
                <span className="text-gray-400 text-sm">{t('paper.aiAnalyzing')}</span>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center py-14 gap-3 text-center">
                <p className="text-red-500 text-sm">{t('paper.aiAnalyzeFailed')}</p>
                <button
                  onClick={onStart}
                  className="px-3 py-1.5 text-xs rounded border border-purple-300 dark:border-purple-700 text-purple-600 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-colors"
                >
                  {t('paper.aiRetry')}
                </button>
              </div>
            ) : content ? (
              <MarkdownRenderer content={content} />
            ) : needsStart ? (
              <div className="flex flex-col items-center justify-center py-14 gap-3 text-center">
                <p className="text-gray-400 text-sm">{t('paper.aiNoContent')}</p>
                <button
                  onClick={onStart}
                  className="px-4 py-2 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 transition-colors"
                >
                  {t('pd.startAnalysis')}
                </button>
              </div>
            ) : (
              <div className="py-14 text-center text-gray-400 text-sm">{t('paper.aiNoContent')}</div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
