'use client';

import { Key, CheckCircle, XCircle, Loader2, Edit3, Trash2, AlertCircle, Settings, RefreshCw } from 'lucide-react';
import type { Dispatch, SetStateAction } from 'react';
import { SettingsInfo } from '@/types/paper';
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
  apiMessage: Record<string, string>;
  updatingKey: string | null;
  onUpdateApiKey: (provider: string) => void;
  setApiKeys: Dispatch<SetStateAction<Record<string, string>>>;
  newProvider: NewProviderInput;
  setNewProvider: Dispatch<SetStateAction<NewProviderInput>>;
  editingProviderName: string | null;
  savingCustomProvider: boolean;
  customProviderMessage: string;
  onEditCustomProvider: (name: string) => void;
  onCancelEditProvider: () => void;
  onSaveCustomProvider: () => void;
  onDeleteCustomProvider: (name: string) => void;
  ports: { backend: number; frontend: number };
  setPorts: Dispatch<SetStateAction<{ backend: number; frontend: number }>>;
  savingPorts: boolean;
  portMessage: string;
  onUpdatePorts: () => void;
  fetchingModels: boolean;
  onFetchModels: () => void;
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
}: ApiConfigPanelProps) {
  const { t } = useLanguage();

  const providers = [
    { key: 'zhipu', label: 'Zhipu' },
    { key: 'openai', label: 'OpenAI' },
    { key: 'siliconflow', label: 'SiliconFlow' },
  ];

  // 只展示已配置 API Key 的 Provider：未配置的卡片一律隐藏，避免界面冗余
  const visibleProviders = providers.filter(provider => settingsInfo?.api_keys?.[provider.key as keyof typeof settingsInfo.api_keys]?.configured);

  return (
    <div className="space-y-6">
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
                  type="password"
                  placeholder={t('sys.newKeyPlaceholder')}
                  value={apiKeys[provider.key] || ''}
                  onChange={e => setApiKeys(prev => ({ ...prev, [provider.key]: e.target.value }))}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                />
                <button
                  onClick={() => onUpdateApiKey(provider.key)}
                  disabled={updatingKey === provider.key || !apiKeys[provider.key]?.trim()}
                  className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
                >
                  {updatingKey === provider.key ? <Loader2 className="w-4 h-4 animate-spin" /> : t('sys.updateBtn')}
                </button>
              </div>
              {apiMessage[provider.key] && (
                <div className={`mt-2 text-xs ${apiMessage[provider.key].includes('成功') ? 'text-green-600' : 'text-red-500'}`}>
                  {apiMessage[provider.key]}
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
                <div className="flex items-center gap-3">
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
              <input
                type="password"
                placeholder={editingProviderName ? t('sys.keepKeyHint') : t('sys.newKeyPlaceholder')}
                value={newProvider.api_key}
                onChange={e => setNewProvider(prev => ({ ...prev, api_key: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
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
              <span className={`text-xs ${customProviderMessage.includes('成功') || customProviderMessage.includes('已') ? 'text-green-600' : 'text-red-500'}`}>
                {customProviderMessage}
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
                value={ports.backend}
                onChange={e => setPorts(prev => ({ ...prev, backend: parseInt(e.target.value) || 8000 }))}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.frontendPort')}</label>
            <div className="flex gap-2">
              <input
                type="number"
                value={ports.frontend}
                onChange={e => setPorts(prev => ({ ...prev, frontend: parseInt(e.target.value) || 3000 }))}
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
            <span className={`text-xs ${portMessage.includes('成功') || portMessage.includes('保存') ? 'text-green-600' : 'text-red-500'}`}>
              {portMessage}
            </span>
          )}
        </div>
        <p className="mt-2 text-xs text-gray-400">{t('sys.portRestartHint')}</p>
      </div>
    </div>
  );
}