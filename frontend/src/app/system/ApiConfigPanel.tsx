'use client';

import { useState, useRef, useEffect } from 'react';
import { Key, CheckCircle, XCircle, Loader2, Edit3, Trash2, RefreshCw, Eye, EyeOff, Download, Upload, Plus, Server } from 'lucide-react';
import type { Dispatch, SetStateAction } from 'react';
import { SettingsInfo, Msg } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

export interface NewProviderInput {
  name: string;
  base_url: string;
  api_key: string;
  models: string;
}

/** 常见 OpenAI 兼容 Provider 预设：选中后自动填入名称与 Base URL */
const PROVIDER_PRESETS = [
  { label: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1' },
  { label: 'Moonshot (Kimi)', baseUrl: 'https://api.moonshot.cn/v1' },
  { label: '阿里云百炼 (Qwen)', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { label: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1' },
  { label: 'Ollama (本机)', baseUrl: 'http://localhost:11434/v1' },
];

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
  // 添加/编辑表单默认收起，点「添加 Provider」或「编辑」时展开
  const [formOpen, setFormOpen] = useState(false);
  const showForm = formOpen || editingProviderName !== null;

  // 保存成功后自动收起表单
  useEffect(() => {
    if (customProviderMessage?.ok) setFormOpen(false);
  }, [customProviderMessage]);

  const providers = [
    { key: 'zhipu', label: 'Zhipu' },
    { key: 'openai', label: 'OpenAI' },
    { key: 'siliconflow', label: 'SiliconFlow' },
  ];

  const isConfigured = (key: string) => !!settingsInfo?.api_keys?.[key as keyof typeof settingsInfo.api_keys]?.configured;
  // 已配置的始终显示；未配置的默认隐藏，用户点「添加」时展开
  const visibleProviders = providers.filter(p => isConfigured(p.key) || revealed[p.key]);
  const hiddenProviders = providers.filter(p => !isConfigured(p.key) && !revealed[p.key]);
  const customProviders = settingsInfo?.custom_providers ?? [];
  const nothingConfigured = visibleProviders.length === 0 && customProviders.length === 0;

  const toggleKeyVisible = (key: string) => setShowKey(prev => ({ ...prev, [key]: !prev[key] }));

  const startAdd = () => {
    setNewProvider({ name: '', base_url: '', api_key: '', models: '' });
    setFormOpen(true);
  };

  const closeForm = () => {
    setFormOpen(false);
    onCancelEditProvider();
  };

  // 预设：自动填入名称（编辑模式下保留原名称）与 Base URL
  const applyPreset = (preset: typeof PROVIDER_PRESETS[number]) => {
    setNewProvider(prev => ({
      ...prev,
      name: editingProviderName ? prev.name : preset.label,
      base_url: preset.baseUrl,
    }));
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border">
      {/* 卡片头：标题 + 导入导出 + 添加按钮 */}
      <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 flex items-center gap-3 flex-wrap">
        <Key className="w-5 h-5 text-purple-600 shrink-0" />
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">{t('sys.providers')}</h2>
          <p className="text-xs text-gray-400 mt-0.5">{t('sys.openaiCompatible')}</p>
        </div>
        <div className="ml-auto flex items-center gap-2 flex-wrap">
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
          <button
            onClick={startAdd}
            disabled={savingCustomProvider}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors"
          >
            <Plus className="w-4 h-4" />
            {t('sys.addProvider')}
          </button>
        </div>
      </div>

      <div className="p-6 space-y-4">
        {/* 空状态：未配置任何服务时的引导占位 */}
        {nothingConfigured && !showForm && (
          <div className="border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-lg p-8 text-center">
            <Server className="w-10 h-10 mx-auto text-gray-300 dark:text-gray-600" />
            <p className="mt-3 text-sm font-medium text-gray-600 dark:text-gray-300">{t('sys.noConfiguredProvider')}</p>
            <p className="mt-1 text-xs text-gray-400">{t('sys.emptyAddDesc')}</p>
            <button
              onClick={startAdd}
              className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 transition-colors"
            >
              <Plus className="w-4 h-4" />
              {t('sys.addProvider')}
            </button>
          </div>
        )}

        {/* 内置 Provider 卡片 */}
        {visibleProviders.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {visibleProviders.map(provider => {
            const status = settingsInfo?.api_keys?.[provider.key as keyof typeof settingsInfo.api_keys];
            return (
              <div key={provider.key} className="bg-gray-50 dark:bg-gray-700/50 rounded-lg border p-5">
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
                  <div className="mb-3 px-3 py-2 bg-white dark:bg-gray-800 rounded text-sm text-gray-600 dark:text-gray-400 font-mono">
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

        {/* 已添加的自定义 Provider */}
        {customProviders.length > 0 && (
          <div className="space-y-3">
            {customProviders.map((cp) => (
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

        {/* 添加 / 编辑表单（默认收起） */}
        {showForm && (
          <div className="border-t dark:border-gray-700 pt-4">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              {editingProviderName ? `${t('sys.editProvider')}: ${editingProviderName}` : t('sys.addNewProvider')}
            </h4>

            {/* 常见 Provider 预设：一键填入名称与 Base URL */}
            <div className="mb-4">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-xs text-gray-500 dark:text-gray-400">{t('sys.presetLabel')}</span>
                <span className="text-xs text-gray-400">{t('sys.presetHint')}</span>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                {PROVIDER_PRESETS.map(preset => {
                  const active = newProvider.base_url === preset.baseUrl;
                  return (
                    <button
                      key={preset.label}
                      type="button"
                      onClick={() => applyPreset(preset)}
                      className={`px-3 py-1.5 text-xs rounded-full border transition-colors ${
                        active
                          ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 font-medium'
                          : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-purple-400 hover:text-purple-600 dark:hover:text-purple-400'
                      }`}
                    >
                      {preset.label}
                    </button>
                  );
                })}
              </div>
            </div>

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
              <button
                onClick={closeForm}
                disabled={savingCustomProvider}
                className="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-sm rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              >
                {t('common.cancel')}
              </button>
              {customProviderMessage && (
                <span className={`text-xs ${customProviderMessage.ok ? 'text-green-600' : 'text-red-500'}`}>
                  {customProviderMessage.text}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
