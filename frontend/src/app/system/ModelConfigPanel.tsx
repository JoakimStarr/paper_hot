'use client';

import { Brain, Loader2, CheckCircle, XCircle, Save, RefreshCw, X } from 'lucide-react';
import type { Dispatch, SetStateAction } from 'react';
import { SettingsInfo } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

export interface TestResult {
  ok: boolean;
  latency_ms?: number;
  message: string;
}

interface ModelConfigPanelProps {
  defaultModel: string | null;
  savingDefaultModel: boolean;
  defaultModelMessage: string;
  embeddingModel: string | null;
  embeddingModelDraft: string;
  setEmbeddingModelDraft: Dispatch<SetStateAction<string>>;
  savingEmbeddingModel: boolean;
  embeddingModelMessage: string;
  modelList: SettingsInfo['models'];
  testResults: Record<string, TestResult>;
  testingModel: string;
  agentEnabled: boolean;
  savingAgent: boolean;
  onToggleAgent: () => void;
  onSaveEmbeddingModel: () => void;
  onClearDefaultModel: () => void;
  onSetDefaultModel: (model: string) => void;
  onTestModelLink: (model: string) => void;
}

export default function ModelConfigPanel({
  defaultModel,
  savingDefaultModel,
  defaultModelMessage,
  embeddingModel,
  embeddingModelDraft,
  setEmbeddingModelDraft,
  savingEmbeddingModel,
  embeddingModelMessage,
  modelList,
  testResults,
  testingModel,
  agentEnabled,
  savingAgent,
  onToggleAgent,
  onSaveEmbeddingModel,
  onClearDefaultModel,
  onSetDefaultModel,
  onTestModelLink,
}: ModelConfigPanelProps) {
  const { t } = useLanguage();

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center gap-3 mb-4">
          <Brain className="w-6 h-6 text-purple-600" />
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('sys.modelConfigTitle')}</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{t('sys.modelConfigDesc')}</p>
          </div>
        </div>

        {/* 当前默认模型 */}
        <div className="mb-6 p-4 bg-purple-50 dark:bg-purple-900/20 border border-purple-100 dark:border-purple-800 rounded-lg">
          <div className="text-xs text-purple-600 dark:text-purple-400 mb-1">{t('sys.defaultModelLabel')}</div>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <span className="text-sm font-semibold text-gray-900 dark:text-white">
              {defaultModel ? (
                <>
                  {defaultModel}
                  <span className="ml-2 text-xs font-normal text-purple-600 dark:text-purple-400">{t('sys.userDefaultModel')}</span>
                </>
              ) : (
                <span className="text-gray-400">{t('sys.defaultNone')}</span>
              )}
            </span>
            {defaultModel && (
              <button
                onClick={onClearDefaultModel}
                disabled={savingDefaultModel}
                className="text-xs text-gray-500 dark:text-gray-400 hover:text-red-500 disabled:opacity-50"
              >
                <X className="w-3.5 h-3.5 inline mr-1" />{t('sys.clearDefault')}
              </button>
            )}
          </div>
          <p className="mt-1 text-xs text-gray-400">{t('sys.defaultModelHint')}</p>
          {defaultModelMessage && (
            <div className={`mt-2 text-xs ${defaultModelMessage.includes('失败') ? 'text-red-500' : 'text-green-600'}`}>
              {defaultModelMessage}
            </div>
          )}
        </div>

        {/* 向量化模型（选题验证器）配置 */}
        <div className="mb-6 p-4 bg-green-50 dark:bg-green-900/20 border border-green-100 dark:border-green-800 rounded-lg">
          <div className="text-xs text-green-700 dark:text-green-400 mb-1">{t('sys.embeddingLabel')}</div>
          <div className="flex items-center gap-2 flex-wrap">
            <input
              value={embeddingModelDraft}
              onChange={(e) => setEmbeddingModelDraft(e.target.value)}
              placeholder={t('sys.embeddingPlaceholder')}
              className="flex-1 min-w-[240px] px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-700 rounded-md text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
            />
            <button
              onClick={onSaveEmbeddingModel}
              disabled={savingEmbeddingModel}
              className="flex items-center gap-1 px-3.5 py-2 text-sm font-medium bg-green-600 hover:bg-green-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-md transition-colors"
            >
              {savingEmbeddingModel ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
              {t('sys.embeddingSave')}
            </button>
          </div>
          <p className="mt-1 text-xs text-gray-400">{t('sys.embeddingHint')}</p>
          {embeddingModelMessage && (
            <div className={`mt-2 text-xs ${embeddingModelMessage.includes('失败') ? 'text-red-500' : 'text-green-600'}`}>
              {embeddingModelMessage}
            </div>
          )}
          {embeddingModel && (
            <div className="mt-2 text-xs text-green-700 dark:text-green-400">
              {t('sys.embeddingCurrent')}: <code className="font-mono bg-green-100 dark:bg-green-900/40 px-1 rounded">{embeddingModel}</code>
            </div>
          )}
        </div>

        {/* AI 追问数据库检索（Agent 工具）开关 */}
        <div className="mb-6 p-4 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-800 rounded-lg">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs text-indigo-700 dark:text-indigo-300 mb-0.5">AI 追问数据库检索（Agent 工具）</div>
              <p className="text-xs text-gray-400">
                开启后，AI 对话可调用工具检索论文库（搜索/语义召回/趋势/空白/作者），
                并实时显示调用进展与 [n] 引用；关闭则保持普通对话。悬浮助手内也可逐会话切换。
              </p>
            </div>
            <button
              onClick={onToggleAgent}
              disabled={savingAgent}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors shrink-0 disabled:opacity-50 ${
                agentEnabled ? 'bg-indigo-600' : 'bg-gray-300 dark:bg-gray-600'
              }`}
              title={agentEnabled ? '点击关闭' : '点击开启'}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  agentEnabled ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
          {savingAgent && <div className="mt-1 text-xs text-gray-400">保存中…</div>}
        </div>

        {/* 模型列表：设为默认 + 测试连接 */}
        <div className="space-y-2">
          {modelList.length === 0 ? (
            <p className="text-sm text-gray-400 py-4">{t('sys.noModels')}</p>
          ) : (
            modelList.map((model) => {
              const test = testResults[model.name];
              const isDefault = defaultModel === model.name;
              return (
                <div key={model.name} className="flex items-center justify-between gap-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg px-4 py-3 flex-wrap">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">{model.name}</span>
                    {model.available ? (
                      <span className="flex items-center gap-1 text-xs text-green-600"><CheckCircle className="w-3.5 h-3.5" />{t('sys.available')}</span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs text-red-500"><XCircle className="w-3.5 h-3.5" />{t('sys.unavailable')}</span>
                    )}
                    {isDefault && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">{t('sys.defaultModelLabel')}</span>
                    )}
                    {test && (
                      <span className={`flex items-center gap-1 text-xs ${test.ok ? 'text-green-600' : 'text-red-500'}`}>
                        {test.ok ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                        {test.ok ? `${t('sys.testResultSuccess')}${test.latency_ms != null ? ` ${test.latency_ms}ms` : ''}` : `${t('sys.testResultFailed')}: ${test.message}`}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => onTestModelLink(model.name)}
                      disabled={testingModel !== ''}
                      className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-200 disabled:opacity-50 transition-colors"
                      title={t('pd.testLink')}
                    >
                      {testingModel === model.name ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                      {t('pd.testLink')}
                    </button>
                    {!isDefault && (
                      <button
                        onClick={() => onSetDefaultModel(model.name)}
                        disabled={savingDefaultModel}
                        className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50 transition-colors"
                      >
                        <Save className="w-3 h-3" />
                        {t('sys.setDefault')}
                      </button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}