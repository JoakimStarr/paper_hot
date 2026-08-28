'use client';

import { X, Loader2 } from 'lucide-react';
import type { Dispatch, SetStateAction } from 'react';
import { Msg } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

interface ModelConfigPanelProps {
  defaultModel: string | null;
  savingDefaultModel: boolean;
  defaultModelMessage: Msg;
  onClearDefaultModel: () => void;
  embeddingModel: string | null;
  embeddingModelDraft: string;
  setEmbeddingModelDraft: Dispatch<SetStateAction<string>>;
  savingEmbeddingModel: boolean;
  embeddingModelMessage: Msg;
  onSaveEmbeddingModel: () => void;
  agentEnabled: boolean;
  savingAgent: boolean;
  agentMessage: Msg;
  onToggleAgent: () => void;
}

/** 使用策略：默认模型 / 嵌入模型 / Agent 开关，三行紧凑布局 */
export default function ModelConfigPanel({
  defaultModel,
  savingDefaultModel,
  defaultModelMessage,
  onClearDefaultModel,
  embeddingModel,
  embeddingModelDraft,
  setEmbeddingModelDraft,
  savingEmbeddingModel,
  embeddingModelMessage,
  onSaveEmbeddingModel,
  agentEnabled,
  savingAgent,
  agentMessage,
  onToggleAgent,
}: ModelConfigPanelProps) {
  const { t } = useLanguage();

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border">
      <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700">
        <h2 className="text-base font-semibold text-gray-900 dark:text-white">{t('sys.usagePolicy')}</h2>
        <p className="text-xs text-gray-400 mt-0.5">{t('sys.usagePolicyDesc')}</p>
      </div>

      <div className="divide-y divide-gray-100 dark:divide-gray-700">
        {/* 默认模型 */}
        <div className="px-6 py-4 flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('sys.defaultModelLabel')}</span>
              {defaultModel ? (
                <code className="text-xs font-mono bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 px-1.5 py-0.5 rounded">{defaultModel}</code>
              ) : (
                <span className="text-xs text-gray-400">{t('sys.defaultNone')}</span>
              )}
            </div>
            <p className="mt-1 text-xs text-gray-400">{t('sys.defaultModelHint')}</p>
            {defaultModelMessage && (
              <div className={`mt-1 text-xs ${defaultModelMessage.ok ? 'text-green-600' : 'text-red-500'}`}>
                {defaultModelMessage.text}
              </div>
            )}
          </div>
          {defaultModel && (
            <button
              onClick={onClearDefaultModel}
              disabled={savingDefaultModel}
              className="shrink-0 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 hover:text-red-500 disabled:opacity-50 transition-colors"
            >
              <X className="w-3.5 h-3.5" />{t('sys.clearDefault')}
            </button>
          )}
        </div>

        {/* 嵌入模型 */}
        <div className="px-6 py-4 flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('sys.embeddingLabel')}</span>
              {embeddingModel && (
                <code className="text-xs font-mono bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300 px-1.5 py-0.5 rounded">{embeddingModel}</code>
              )}
            </div>
            <p className="mt-1 text-xs text-gray-400">{t('sys.embeddingHint')}</p>
            {embeddingModelMessage && (
              <div className={`mt-1 text-xs ${embeddingModelMessage.ok ? 'text-green-600' : 'text-red-500'}`}>
                {embeddingModelMessage.text}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <input
              value={embeddingModelDraft}
              onChange={(e) => setEmbeddingModelDraft(e.target.value)}
              placeholder={t('sys.embeddingPlaceholder')}
              className="w-56 max-w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 dark:bg-gray-700 rounded-md text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
            />
            <button
              onClick={onSaveEmbeddingModel}
              disabled={savingEmbeddingModel}
              className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium bg-green-600 hover:bg-green-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-md transition-colors"
            >
              {savingEmbeddingModel && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              {t('sys.embeddingSave')}
            </button>
          </div>
        </div>

        {/* Agent 检索开关 */}
        <div className="px-6 py-4 flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0 max-w-2xl">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('sys.agentTitle')}</span>
            <p className="mt-1 text-xs text-gray-400">{t('sys.agentDesc')}</p>
            {agentMessage && (
              <div className={`mt-1 text-xs ${agentMessage.ok ? 'text-green-600' : 'text-red-500'}`}>
                {agentMessage.text}
              </div>
            )}
          </div>
          <button
            onClick={onToggleAgent}
            disabled={savingAgent}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors shrink-0 disabled:opacity-50 ${
              agentEnabled ? 'bg-indigo-600' : 'bg-gray-300 dark:bg-gray-600'
            }`}
            title={agentEnabled ? t('sys.agentOn') : t('sys.agentOff')}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                agentEnabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
      </div>
    </div>
  );
}
