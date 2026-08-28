'use client';

import type { Dispatch, SetStateAction } from 'react';
import { Settings, Loader2, RotateCcw } from 'lucide-react';
import { SettingsInfo, Msg } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';
import ApiConfigPanel, { NewProviderInput } from './ApiConfigPanel';
import ModelConfigPanel from './ModelConfigPanel';
import ModelPriorityPanel, { TestResult } from './ModelPriorityPanel';

interface ModelConfigTabProps {
  settingsInfo: SettingsInfo | null;
  apiKeys: Record<string, string>;
  apiMessage: Record<string, Msg>;
  updatingKey: string | null;
  onUpdateApiKey: (provider: string) => void;
  setApiKeys: Dispatch<SetStateAction<Record<string, string>>>;
  newProvider: NewProviderInput;
  setNewProvider: Dispatch<SetStateAction<NewProviderInput>>;
  editingProviderName: string | null;
  savingCustomProvider: boolean;
  customProviderMessage: Msg;
  onEditCustomProvider: (name: string) => void;
  onCancelEditProvider: () => void;
  onSaveCustomProvider: () => void;
  onDeleteCustomProvider: (name: string) => void;
  ports: { backend: number; frontend: number };
  setPorts: Dispatch<SetStateAction<{ backend: number; frontend: number }>>;
  savingPorts: boolean;
  portMessage: Msg;
  onUpdatePorts: () => void;
  modelList: SettingsInfo['models'];
  savingModels: boolean;
  modelMessage: Msg;
  onSaveModelPriority: () => void;
  onMoveModel: (index: number, direction: 'up' | 'down') => void;
  onReorderModel: (from: number, to: number) => void;
  defaultModel: string | null;
  savingDefaultModel: boolean;
  defaultModelMessage: Msg;
  embeddingModel: string | null;
  embeddingModelDraft: string;
  setEmbeddingModelDraft: Dispatch<SetStateAction<string>>;
  savingEmbeddingModel: boolean;
  embeddingModelMessage: Msg;
  onSaveEmbeddingModel: () => void;
  onClearDefaultModel: () => void;
  onSetDefaultModel: (model: string) => void;
  testingModel: string;
  testResults: Record<string, TestResult>;
  onTestModelLink: (model: string) => void;
  agentEnabled: boolean;
  savingAgent: boolean;
  agentMessage: Msg;
  onToggleAgent: () => void;
  fetchingModels: boolean;
  onFetchModels: () => void;
  onExportConfig: () => void;
  onImportConfig: (file: File) => void;
  onRestartService: () => void;
}

export default function ModelConfigTab({
  settingsInfo,
  apiKeys,
  apiMessage,
  updatingKey,
  onUpdateApiKey,
  setApiKeys,
  newProvider,
  setNewProvider,
  editingProviderName,
  savingCustomProvider,
  customProviderMessage,
  onEditCustomProvider,
  onCancelEditProvider,
  onSaveCustomProvider,
  onDeleteCustomProvider,
  ports,
  setPorts,
  savingPorts,
  portMessage,
  onUpdatePorts,
  modelList,
  savingModels,
  modelMessage,
  onSaveModelPriority,
  onMoveModel,
  onReorderModel,
  defaultModel,
  savingDefaultModel,
  defaultModelMessage,
  embeddingModel,
  embeddingModelDraft,
  setEmbeddingModelDraft,
  savingEmbeddingModel,
  embeddingModelMessage,
  onSaveEmbeddingModel,
  onClearDefaultModel,
  onSetDefaultModel,
  testingModel,
  testResults,
  onTestModelLink,
  agentEnabled,
  savingAgent,
  agentMessage,
  onToggleAgent,
  fetchingModels,
  onFetchModels,
  onExportConfig,
  onImportConfig,
  onRestartService,
}: ModelConfigTabProps) {
  const { t } = useLanguage();

  // 状态横幅：AI 可用性 / 默认模型 / 已配置服务数
  const aiAvailable = !!settingsInfo?.models?.some(m => m.available);
  const configuredCount =
    (settingsInfo?.api_keys
      ? Object.values(settingsInfo.api_keys).filter(k => k.configured).length
      : 0) +
    (settingsInfo?.custom_providers?.filter(p => p.api_key_configured).length ?? 0);

  return (
    <div className="space-y-6">
      {/* 状态横幅 */}
      <div className="rounded-lg border border-purple-100 dark:border-purple-800 bg-gradient-to-r from-purple-50 to-indigo-50 dark:from-purple-900/20 dark:to-indigo-900/20 px-5 py-3.5 flex items-center gap-3 flex-wrap">
        <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${aiAvailable ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
        <span className={`text-sm font-medium ${aiAvailable ? 'text-green-600' : 'text-red-500'}`}>
          {aiAvailable ? t('sys.aiAvailable') : t('sys.aiUnavailable')}
        </span>
        <span className="text-gray-300 dark:text-gray-600">|</span>
        <span className="text-sm text-gray-600 dark:text-gray-300">
          {t('sys.defaultModelLabel')}:
          {defaultModel ? (
            <code className="ml-1.5 text-xs font-mono text-purple-700 dark:text-purple-300">{defaultModel}</code>
          ) : (
            <span className="ml-1.5 text-xs text-gray-400">{t('sys.defaultNone')}</span>
          )}
        </span>
        <span className="ml-auto text-xs text-gray-500 dark:text-gray-400">
          {t('sys.configuredServices', { n: configuredCount })}
        </span>
      </div>

      {/* API 服务：内置 / 自定义 Provider + 配置导入导出 */}
      <ApiConfigPanel
        settingsInfo={settingsInfo}
        apiKeys={apiKeys}
        apiMessage={apiMessage}
        updatingKey={updatingKey}
        onUpdateApiKey={onUpdateApiKey}
        setApiKeys={setApiKeys}
        newProvider={newProvider}
        setNewProvider={setNewProvider}
        editingProviderName={editingProviderName}
        savingCustomProvider={savingCustomProvider}
        customProviderMessage={customProviderMessage}
        onEditCustomProvider={onEditCustomProvider}
        onCancelEditProvider={onCancelEditProvider}
        onSaveCustomProvider={onSaveCustomProvider}
        onDeleteCustomProvider={onDeleteCustomProvider}
        fetchingModels={fetchingModels}
        onFetchModels={onFetchModels}
        onExportConfig={onExportConfig}
        onImportConfig={onImportConfig}
      />

      {/* 使用策略：默认模型 / 嵌入模型 / Agent 开关 */}
      <ModelConfigPanel
        defaultModel={defaultModel}
        savingDefaultModel={savingDefaultModel}
        defaultModelMessage={defaultModelMessage}
        onClearDefaultModel={onClearDefaultModel}
        embeddingModel={embeddingModel}
        embeddingModelDraft={embeddingModelDraft}
        setEmbeddingModelDraft={setEmbeddingModelDraft}
        savingEmbeddingModel={savingEmbeddingModel}
        embeddingModelMessage={embeddingModelMessage}
        onSaveEmbeddingModel={onSaveEmbeddingModel}
        agentEnabled={agentEnabled}
        savingAgent={savingAgent}
        agentMessage={agentMessage}
        onToggleAgent={onToggleAgent}
      />

      {/* 模型管理：优先级排序 + 设为默认 + 测试连接（单一列表） */}
      <ModelPriorityPanel
        modelList={modelList}
        savingModels={savingModels}
        modelMessage={modelMessage}
        settingsInfo={settingsInfo}
        onSaveModelPriority={onSaveModelPriority}
        onMoveModel={onMoveModel}
        onReorderModel={onReorderModel}
        defaultModel={defaultModel}
        savingDefaultModel={savingDefaultModel}
        onSetDefaultModel={onSetDefaultModel}
        testingModel={testingModel}
        testResults={testResults}
        onTestModelLink={onTestModelLink}
      />

      {/* 系统参数：端口配置 + 服务操作 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border">
        <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 flex items-center gap-2">
          <Settings className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          <div>
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">{t('sys.systemParams')}</h2>
            <p className="text-xs text-gray-400 mt-0.5">{t('sys.systemParamsDesc')}</p>
          </div>
        </div>
        <div className="p-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 端口配置 */}
          <div className="flex flex-col">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('sys.portConfig')}</div>
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.backendPort')}</label>
                <input
                  type="number"
                  min={1}
                  max={65535}
                  value={ports.backend}
                  onChange={e => {
                    const v = parseInt(e.target.value);
                    setPorts(prev => ({ ...prev, backend: Number.isNaN(v) ? prev.backend : v }));
                  }}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.frontendPort')}</label>
                <input
                  type="number"
                  min={1}
                  max={65535}
                  value={ports.frontend}
                  onChange={e => {
                    const v = parseInt(e.target.value);
                    setPorts(prev => ({ ...prev, frontend: Number.isNaN(v) ? prev.frontend : v }));
                  }}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
            <div className="mt-3 flex items-center gap-3 flex-wrap">
              <button
                onClick={onUpdatePorts}
                disabled={savingPorts}
                className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
              >
                {savingPorts ? <Loader2 className="w-4 h-4 animate-spin" /> : t('common.save')}
              </button>
              {portMessage && (
                <span className={`text-xs ${portMessage.ok ? 'text-green-600' : 'text-red-500'}`}>
                  {portMessage.text}
                </span>
              )}
            </div>
            <p className="mt-auto pt-3 text-xs text-gray-400">{t('sys.portRestartHint')}：{t('sys.portRestartCmdHint')}</p>
            <code className="mt-1 self-start px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 text-xs font-mono text-gray-700 dark:text-gray-200">./stop.sh &amp;&amp; ./start.sh</code>
          </div>

          {/* 服务操作：一键重启 */}
          <div className="flex flex-col lg:pl-6 lg:border-l border-gray-100 dark:border-gray-700">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('sys.serviceOps')}</div>
            <p className="mt-3 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{t('sys.restartDesc')}</p>
            <button
              onClick={onRestartService}
              className="mt-3 self-start flex items-center gap-2 px-4 py-2 border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
              {t('sys.restartService')}
            </button>
            <p className="mt-auto pt-3 text-xs text-gray-400">{t('sys.restartHint')}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
