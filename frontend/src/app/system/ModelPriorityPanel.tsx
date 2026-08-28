'use client';

import { useRef, useState } from 'react';
import { Brain, Save, Loader2, CheckCircle, XCircle, ArrowUp, ArrowDown, Activity, GripVertical } from 'lucide-react';
import { SettingsInfo, Msg } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

interface ModelPriorityPanelProps {
  modelList: SettingsInfo['models'];
  savingModels: boolean;
  modelMessage: Msg;
  settingsInfo: SettingsInfo | null;
  onSaveModelPriority: () => void;
  onMoveModel: (index: number, direction: 'up' | 'down') => void;
  onReorderModel: (from: number, to: number) => void;
}

export default function ModelPriorityPanel({
  modelList,
  savingModels,
  modelMessage,
  settingsInfo,
  onSaveModelPriority,
  onMoveModel,
  onReorderModel,
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
          <div className={`mb-4 p-3 rounded-lg text-sm ${modelMessage.ok ? 'bg-green-50 dark:bg-green-900/30 text-green-600' : 'bg-red-50 dark:bg-red-900/30 text-red-600'}`}>
            {modelMessage.text}
          </div>
        )}
        <div className="space-y-2">
          {modelList.map((model, index) => (
            <div
              key={model.name}
              draggable
              onDragStart={handleDragStart(index)}
              onDragOver={handleDragOver(index)}
              onDragLeave={() => setDragOverIndex(prev => (prev === index ? null : prev))}
              onDrop={handleDrop(index)}
              onDragEnd={handleDragEnd}
              className={`flex items-center justify-between bg-gray-50 dark:bg-gray-700/50 rounded-lg px-4 py-3 transition-opacity ${
                dragIndex === index ? 'opacity-40' : ''
              } ${dragOverIndex === index && dragIndex !== null && dragIndex !== index ? 'ring-2 ring-primary-400' : ''}`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <GripVertical className="w-4 h-4 shrink-0 text-gray-300 dark:text-gray-500 cursor-grab active:cursor-grabbing" aria-hidden />
                <span className="w-7 h-7 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-xs font-bold shrink-0">
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
                {model.available ? (
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
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => onMoveModel(index, 'up')}
                  disabled={index === 0}
                  className="p-1.5 hover:bg-gray-200 rounded disabled:opacity-30 transition-colors"
                  title={t('sys.moveUp')}
                >
                  <ArrowUp className="w-4 h-4" />
                </button>
                <button
                  onClick={() => onMoveModel(index, 'down')}
                  disabled={index === modelList.length - 1}
                  className="p-1.5 hover:bg-gray-200 rounded disabled:opacity-30 transition-colors"
                  title={t('sys.moveDown')}
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
