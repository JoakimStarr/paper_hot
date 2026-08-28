'use client';

import { useState, useRef } from 'react';
import { Key, CheckCircle, XCircle, Loader2, Edit3, Trash2, AlertCircle, Settings, RefreshCw, Eye, EyeOff, Download, Upload, Plus } from 'lucide-react';
import type { Dispatch, SetStateAction } from 'react';
import { SettingsInfo, Msg } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

export interface NewProviderInput {
  name: string;
  base_url: string;
  api_key: string;
  models: string;
}

interface ApiConfigPanelProps {
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
  fetchingModels: boolean;
  onFetchModels: () => void;
  onExportConfig: () => void;
  onImportConfig: (file: File) => void;
}

export default function ApiConfigPanel({
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
  fetchingModels,
  onFetchModels,
  onExportConfig,
  onImportConfig,
}: ApiConfigPanelProps) {
  const { t } = useLanguage();
  const importFileRef = useRef<HTMLInputElement>(null);

  // 未配置内置 Provider 的展示开关：默认隐藏，点「添加」展开对应卡片
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  // API Key 明文切换
  const [showKey, setShowKey] = useState<Record<string, boolean>>({});
  const [showNewKey, setShowNewKey] = useState(false);

  const providers = [
    { key: 'zhipu', label: 'Zhipu' },
    { key: 'openai', label: 'OpenAI' },
    { key: 'siliconflow', label: 'SiliconFlow' },
  ];

  const isConfigured = (key: string) => !!settingsInfo?.api_keys?.[key as keyof typeof settingsInfo.api_keys]?.configured;
  // 已配置的始终显示；未配置的默认隐藏，用户点「添加」时展开
  const visibleProviders = providers.filter(p => isConfigured(p.key) || revealed[p.key]);
  const hiddenProviders = providers.filter(p => !isConfigured(p.key) && !revealed[p.key]);

  const toggleKeyVisible = (key: string) => setShowKey(prev => ({ ...prev, [key]: !prev[key] }));

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        {/* 配置导出/导入 */}
        <div className="flex items-center justify-end gap-2 flex-wrap">
          <button
            onClick={onExportConfig}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-primary-400 transition-colors"
            title={t('sys.exportConfigHint')}
          >
            <Download className="w-3.5 h-3.5" />
            {t('sys.exportConfig')}
          </button>
          <button
            onClick={() => importFileRef.current?.click()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-primary-400 transition-colors"
          >
            <Upload className="w-3.5 h-3.5" />
            {t('sys.importConfig')}
          </button>
          <input
            ref={importFileRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onImportConfig(file);
              e.target.value = '';
            }}
          />
        </div>

        {visibleProviders.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {visibleProviders.map(provider => {
            const status = settingsInfo?.api_keys?.[provider.key as keyof typeof settingsInfo.api_keys];
            return (
              <div key={provider.key} className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Key className="w-5 h-5 text-primary-600" />
                    <h3 className="font-semibold text-gray-900 dark:text-white">{provider.label}</h3>
                  </div>
                  {status?.configured ? (
                    <span className="flex items-center gap-1 text-xs font-medium text-green-600">
                      <CheckCircle className="w-4 h-4" />
                      {t('sys.configured')}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs font-medium text-red-500">
                      <XCircle className="w-4 h-4" />
                      {t('sys.notConfigured')}
                    </span>
                  )}
                </div>
                {status?.masked && (
                  <div className="mb-3 px-3 py-2 bg-gray-50 dark:bg-gray-700/50 rounded text-sm text-gray-600 dark:text-gray-400 font-mono">
                    {status.masked}
                  </div>
                )}
                <div className="flex gap-2">
                  <input
                    type={showKey[provider.key] ? 'text' : 'password'}
                    placeholder={t('sys.newKeyPlaceholder')}
                    value={apiKeys[provider.key] || ''}
                    onChange={e => setApiKeys(prev => ({ ...prev, [provider.key]: e.target.value }))}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                  <button
                    onClick={() => toggleKeyVisible(provider.key)}
                    className="px-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                    title={showKey[provider.key] ? t('sys.hideKey') : t('sys.showKey')}
                  >
                    {showKey[provider.key] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                  <button
                    onClick={() => onUpdateApiKey(provider.key)}
                    disabled={updatingKey === provider.key || !apiKeys[provider.key]?.trim()}
                    className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
                  >
                    {updatingKey === provider.key ? <Loader2 className="w-4 h-4 animate-spin" /> : t('sys.updateBtn')}
                  </button>
                </div>
                {apiMessage[provider.key] && (
                  <div className={`mt-2 text-xs ${apiMessage[provider.key]!.ok ? 'text-green-600' : 'text-red-500'}`}>
                    {apiMessage[provider.key]!.text}
                  </div>
                )}
              </div>
            );
          })}
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6 text-sm text-gray-400 dark:text-gray-500">
            {t('sys.noConfiguredProvider')}
          </div>
        )}

        {/* 未配置的内置服务：折叠入口，点击展开配置卡片 */}
        {hiddenProviders.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap text-xs text-gray-500 dark:text-gray-400">
            <span>{t('sys.unconfiguredBuiltin')}:</span>
            {hiddenProviders.map(p => (
              <button
                key={p.key}
                onClick={() => setRevealed(prev => ({ ...prev, [p.key]: true }))}
                className="flex items-center gap-1 px-2 py-1 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 hover:border-primary-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
              >
                <Plus className="w-3 h-3" />
                {p.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Custom Providers Section */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Key className="w-5 h-5 text-purple-600" />
            <h3 className="font-semibold text-gray-900 dark:text-white">{t('sys.customProviders')}</h3>
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400">{t('sys.openaiCompatible')}</span>
        </div>

        {/* Existing custom providers */}
        {settingsInfo?.custom_providers && settingsInfo.custom_providers.length > 0 && (
          <div className="mb-4 space-y-3">
            {settingsInfo.custom_providers.map((cp) => (
              <div key={cp.name} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <div className="flex items-center gap-3 min-w-0 flex-wrap">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900 dark:text-white">{cp.name}</span>
                    {cp.api_key_configured ? (
                      <span className="flex items-center gap-1 text-xs text-green-600">
                        <CheckCircle className="w-3 h-3" />
                        {t('sys.configured')}
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs text-red-500">
                        <XCircle className="w-3 h-3" />
                        {t('sys.notConfigured')}
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">{cp.base_url}</span>
                  {cp.models.length > 0 && (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {t('sys.modelsInline')}{cp.models.join(', ')}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => onEditCustomProvider(cp.name)}
                    disabled={savingCustomProvider}
                    className="p-1 text-gray-500 hover:text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-900/20 rounded transition-colors"
                    title={t('sys.editProvider')}
                  >
                    <Edit3 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => onDeleteCustomProvider(cp.name)}
                    disabled={savingCustomProvider}
                    className="p-1 text-red-500 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Add / edit custom provider */}
        <div className="border-t dark:border-gray-700 pt-4">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            {editingProviderName ? `${t('sys.editProvider')}: ${editingProviderName}` : t('sys.addNewProvider')}
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.nameLabel')} *</label>
              <input
                type="text"
                placeholder="my-llm"
                value={newProvider.name}
                onChange={e => setNewProvider(prev => ({ ...prev, name: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.baseUrlLabel')}</label>
              <input
                type="text"
                placeholder={t('sys.baseUrlPlaceholder')}
                value={newProvider.base_url}
                onChange={e => setNewProvider(prev => ({ ...prev, base_url: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                {t('sys.apiKeyLabel')}{editingProviderName ? ` (${t('sys.keepKeyHint')})` : '*'}
              </label>
              <div className="flex gap-2">
                <input
                  type={showNewKey ? 'text' : 'password'}
                  placeholder={editingProviderName ? t('sys.keepKeyHint') : t('sys.newKeyPlaceholder')}
                  value={newProvider.api_key}
                  onChange={e => setNewProvider(prev => ({ ...prev, api_key: e.target.value }))}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <button
                  onClick={() => setShowNewKey(v => !v)}
                  className="px-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                  title={showNewKey ? t('sys.hideKey') : t('sys.showKey')}
                >
                  {showNewKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs text-gray-500 dark:text-gray-400">{t('sys.modelsLabel')}</label>
                <button
                  type="button"
                  onClick={onFetchModels}
                  disabled={fetchingModels}
                  className="flex items-center gap-1 text-xs text-purple-600 dark:text-purple-300 hover:underline disabled:opacity-50 disabled:hover:no-underline"
                  title={t('sys.fetchModelsHelper')}
                >
                  {fetchingModels ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                  {t('sys.fetchModels')}
                </button>
              </div>
              <input
                type="text"
                placeholder={t('sys.modelsPlaceholder')}
                value={newProvider.models}
                onChange={e => setNewProvider(prev => ({ ...prev, models: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button
              onClick={onSaveCustomProvider}
              disabled={savingCustomProvider || !newProvider.name.trim() || !newProvider.base_url.trim() || (!editingProviderName && !newProvider.api_key.trim())}
              className="px-4 py-2 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors"
            >
              {savingCustomProvider ? <Loader2 className="w-4 h-4 animate-spin" /> : (editingProviderName ? t('sys.saveChanges') : t('sys.addProvider'))}
            </button>
            {editingProviderName && (
              <button
                onClick={onCancelEditProvider}
                disabled={savingCustomProvider}
                className="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-sm rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              >
                {t('common.cancel')}
              </button>
            )}
            {customProviderMessage && (
              <span className={`text-xs ${customProviderMessage.ok ? 'text-green-600' : 'text-red-500'}`}>
                {customProviderMessage.text}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center gap-2">
          <AlertCircle className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('sys.tokenStatus')}</span>
        </div>
        <div className="mt-2">
          {settingsInfo?.api_token_configured ? (
            <span className="flex items-center gap-1 text-sm text-green-600">
              <CheckCircle className="w-4 h-4" />
              {t('sys.tokenConfigured')}
            </span>
          ) : (
            <span className="flex items-center gap-1 text-sm text-red-500">
              <XCircle className="w-4 h-4" />
              {t('sys.tokenNotConfigured')}
            </span>
          )}
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center gap-2 mb-4">
          <Settings className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('sys.portConfig')}</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.backendPort')}</label>
            <div className="flex gap-2">
              <input
                type="number"
                min={1}
                max={65535}
                value={ports.backend}
                onChange={e => {
                  const v = parseInt(e.target.value);
                  setPorts(prev => ({ ...prev, backend: Number.isNaN(v) ? prev.backend : v }));
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.frontendPort')}</label>
            <div className="flex gap-2">
              <input
                type="number"
                min={1}
                max={65535}
                value={ports.frontend}
                onChange={e => {
                  const v = parseInt(e.target.value);
                  setPorts(prev => ({ ...prev, frontend: Number.isNaN(v) ? prev.frontend : v }));
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-3">
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
        <p className="mt-2 text-xs text-gray-400">{t('sys.portRestartHint')}</p>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{t('sys.portRestartCmdHint')}</p>
        <code className="inline-block mt-1 px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 text-xs font-mono text-gray-700 dark:text-gray-200">./stop.sh &amp;&amp; ./start.sh</code>
      </div>
    </div>
  );
}
