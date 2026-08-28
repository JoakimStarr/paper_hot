'use client';

import { useRef, useState } from 'react';
import { Save, Loader2, CheckCircle, XCircle, ArrowUp, ArrowDown, GripVertical, RefreshCw } from 'lucide-react';
import { SettingsInfo, Msg } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

export interface TestResult {
  ok: boolean;
  latency_ms?: number;
  message: string;
}

interface ModelPriorityPanelProps {
  modelList: SettingsInfo['models'];
  savingModels: boolean;
  modelMessage: Msg;
  settingsInfo: SettingsInfo | null;
  onSaveModelPriority: () => void;
  onMoveModel: (index: number, direction: 'up' | 'down') => void;
  onReorderModel: (from: number, to: number) => void;
  defaultModel: string | null;
  savingDefaultModel: boolean;
  onSetDefaultModel: (model: string) => void;
  testingModel: string;
  testResults: Record<string, TestResult>;
  onTestModelLink: (model: string) => void;
}

/** 模型管理：单一列表同时承载优先级排序（拖拽/箭头）、设为默认、测试连接 */
export default function ModelPriorityPanel({
  modelList,
  savingModels,
  modelMessage,
  settingsInfo,
  onSaveModelPriority,
  onMoveModel,
  onReorderModel,
  defaultModel,
  savingDefaultModel,
  onSetDefaultModel,
  testingModel,
  testResults,
  onTestModelLink,
}: ModelPriorityPanelProps) {
  const { t } = useLanguage();
  // 拖拽排序状态：dragIndex 为被拖项，dragOverIndex 为当前悬停目标（高亮插入位置）
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const dragIndexRef = useRef<number | null>(null);

  const handleDragStart = (index: number) => (e: React.DragEvent) => {
    dragIndexRef.current = index;
    setDragIndex(index);
    e.dataTransfer.effectAllowed = 'move';
    // Firefox 需要 setData 才会触发 drag 事件
    e.dataTransfer.setData('text/plain', String(index));
  };

  const handleDragOver = (index: number) => (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverIndex(index);
  };

  const handleDrop = (index: number) => (e: React.DragEvent) => {
    e.preventDefault();
    const from = dragIndexRef.current;
    if (from !== null && from !== index) onReorderModel(from, index);
    dragIndexRef.current = null;
    setDragIndex(null);
    setDragOverIndex(null);
  };

  const handleDragEnd = () => {
    dragIndexRef.current = null;
    setDragIndex(null);
    setDragOverIndex(null);
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border">
      <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">{t('sys.modelManage')}</h2>
          <p className="text-xs text-gray-400 mt-0.5 max-w-2xl">{t('sys.modelManageDesc')}</p>
        </div>
        <div className="flex items-center gap-3">
          {modelMessage && (
            <span className={`text-xs ${modelMessage.ok ? 'text-green-600' : 'text-red-500'}`}>
              {modelMessage.text}
            </span>
          )}
          <button
            onClick={onSaveModelPriority}
            disabled={savingModels}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors shrink-0"
          >
            {savingModels ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {t('sys.saveOrder')}
          </button>
        </div>
      </div>

      <div className="p-6 space-y-2">
        {modelList.map((model, index) => {
          const test = testResults[model.name];
          const isDefault = defaultModel === model.name;
          return (
            <div
              key={model.name}
              draggable
              onDragStart={handleDragStart(index)}
              onDragOver={handleDragOver(index)}
              onDragLeave={() => setDragOverIndex(prev => (prev === index ? null : prev))}
              onDrop={handleDrop(index)}
              onDragEnd={handleDragEnd}
              className={`flex items-center justify-between gap-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg px-3 py-2.5 transition-opacity ${
                dragIndex === index ? 'opacity-40' : ''
              } ${dragOverIndex === index && dragIndex !== null && dragIndex !== index ? 'ring-2 ring-primary-400' : ''}`}
            >
              <div className="flex items-center gap-2.5 min-w-0 flex-wrap">
                <GripVertical className="w-4 h-4 shrink-0 text-gray-300 dark:text-gray-500 cursor-grab active:cursor-grabbing" aria-hidden />
                <span className="w-6 h-6 rounded-full bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 flex items-center justify-center text-xs font-bold shrink-0">
                  {index + 1}
                </span>
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">{model.name}</span>
                {model.provider && (
                  <span className={`text-xs px-1.5 py-0.5 rounded shrink-0 ${
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
                {isDefault ? (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-purple-600 text-white shrink-0">{t('sys.defaultChip')}</span>
                ) : model.available ? (
                  <span className="flex items-center gap-1 text-xs text-green-600 shrink-0">
                    <CheckCircle className="w-3.5 h-3.5" />
                    {t('sys.available')}
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs text-red-500 shrink-0">
                    <XCircle className="w-3.5 h-3.5" />
                    {t('sys.unavailable')}
                  </span>
                )}
                {test && (
                  <span className={`flex items-center gap-1 text-xs shrink-0 ${test.ok ? 'text-green-600' : 'text-red-500'}`}>
                    {test.ok ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                    {test.ok
                      ? `${t('sys.testResultSuccess')}${test.latency_ms != null ? ` ${test.latency_ms}ms` : ''}`
                      : `${t('sys.testResultFailed')}: ${test.message}`}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => onTestModelLink(model.name)}
                  disabled={testingModel !== ''}
                  className="flex items-center gap-1 px-2 py-1.5 text-xs text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 disabled:opacity-50 transition-colors"
                  title={t('pd.testLink')}
                >
                  {testingModel === model.name ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                  {t('pd.testLink')}
                </button>
                {!isDefault && (
                  <button
                    onClick={() => onSetDefaultModel(model.name)}
                    disabled={savingDefaultModel}
                    className="px-2 py-1.5 text-xs text-purple-600 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/20 rounded disabled:opacity-50 transition-colors"
                  >
                    {t('sys.setDefault')}
                  </button>
                )}
                <div className="flex flex-col">
                  <button
                    onClick={() => onMoveModel(index, 'up')}
                    disabled={index === 0}
                    className="p-0.5 hover:bg-gray-200 dark:hover:bg-gray-600 rounded disabled:opacity-30 transition-colors"
                    title={t('sys.moveUp')}
                  >
                    <ArrowUp className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => onMoveModel(index, 'down')}
                    disabled={index === modelList.length - 1}
                    className="p-0.5 hover:bg-gray-200 dark:hover:bg-gray-600 rounded disabled:opacity-30 transition-colors"
                    title={t('sys.moveDown')}
                  >
                    <ArrowDown className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
        {modelList.length === 0 && (
          <p className="text-sm text-gray-400 py-4">{t('sys.noModels')}</p>
        )}
      </div>
    </div>
  );
}
