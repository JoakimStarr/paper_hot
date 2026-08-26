'use client';

import { Brain, Save, Loader2, CheckCircle, XCircle, ArrowUp, ArrowDown, Activity } from 'lucide-react';
import { SettingsInfo } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

interface ModelPriorityPanelProps {
  modelList: SettingsInfo['models'];
  savingModels: boolean;
  modelMessage: string;
  settingsInfo: SettingsInfo | null;
  onSaveModelPriority: () => void;
  onMoveModel: (index: number, direction: 'up' | 'down') => void;
}

export default function ModelPriorityPanel({
  modelList,
  savingModels,
  modelMessage,
  settingsInfo,
  onSaveModelPriority,
  onMoveModel,
}: ModelPriorityPanelProps) {
  const { t } = useLanguage();

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Brain className="w-6 h-6 text-primary-600" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('sys.modelPriority')}</h2>
          </div>
          <button
            onClick={onSaveModelPriority}
            disabled={savingModels}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
          >
            {savingModels ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {t('sys.saveOrder')}
          </button>
        </div>
        {modelMessage && (
          <div className={`mb-4 p-3 rounded-lg text-sm ${modelMessage.includes('失败') ? 'bg-red-50 dark:bg-red-900/30 text-red-600' : 'bg-green-50 dark:bg-green-900/30 text-green-600'}`}>
            {modelMessage}
          </div>
        )}
        <div className="space-y-2">
          {modelList.map((model, index) => (
            <div key={model.name} className="flex items-center justify-between bg-gray-50 dark:bg-gray-700/50 rounded-lg px-4 py-3">
              <div className="flex items-center gap-3">
                <span className="w-7 h-7 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-xs font-bold">
                  {index + 1}
                </span>
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{model.name}</span>
                {model.provider && (
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    model.provider === 'siliconflow'
                      ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
                      : model.provider === 'zhipu'
                        ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400'
                        : model.provider === 'openai'
                          ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400'
                          : 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400'
                  }`}>
                    {model.provider === 'siliconflow' ? t('sys.providerSiliconflow') : model.provider === 'zhipu' ? t('sys.providerZhipu') : model.provider === 'openai' ? 'OpenAI' : model.provider}
                  </span>
                )}
                {model.available ? (
                  <span className="flex items-center gap-1 text-xs text-green-600">
                    <CheckCircle className="w-3.5 h-3.5" />
                    {t('sys.available')}
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs text-red-500">
                    <XCircle className="w-3.5 h-3.5" />
                    {t('sys.unavailable')}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => onMoveModel(index, 'up')}
                  disabled={index === 0}
                  className="p-1.5 hover:bg-gray-200 rounded disabled:opacity-30 transition-colors"
                >
                  <ArrowUp className="w-4 h-4" />
                </button>
                <button
                  onClick={() => onMoveModel(index, 'down')}
                  disabled={index === modelList.length - 1}
                  className="p-1.5 hover:bg-gray-200 rounded disabled:opacity-30 transition-colors"
                >
                  <ArrowDown className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
          {modelList.length === 0 && (
            <p className="text-sm text-gray-400 py-4">{t('sys.noModels')}</p>
          )}
        </div>
        <p className="mt-3 text-xs text-gray-400">{t('sys.customOrderHint')}</p>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('sys.aiServiceStatus')}</span>
        </div>
        <div className="mt-2">
          {settingsInfo?.models?.some(m => m.available) ? (
            <span className="flex items-center gap-1 text-sm text-green-600">
              <CheckCircle className="w-4 h-4" />
              {t('sys.aiAvailable')}
            </span>
          ) : (
            <span className="flex items-center gap-1 text-sm text-red-500">
              <XCircle className="w-4 h-4" />
              {t('sys.aiUnavailable')}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}