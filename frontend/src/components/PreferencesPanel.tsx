'use client';

import React, { useState } from 'react';
import { EyeOff, Plus, X, Loader2 } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { useToast } from '@/components/Toast';
import { usePreferences } from '@/lib/usePreferences';

type PrefType = 'subfield' | 'journal' | 'keyword' | 'author';

const PREF_TYPES: Array<{ type: PrefType; labelKey: string }> = [
  { type: 'subfield', labelKey: 'pref.type.subfield' },
  { type: 'journal', labelKey: 'pref.type.journal' },
  { type: 'keyword', labelKey: 'pref.type.keyword' },
  { type: 'author', labelKey: 'pref.type.author' },
];

/**
 * 「不感兴趣」屏蔽管理：按类型增删领域/期刊/关键词/作者，全局列表过滤生效。
 * 首页与工作台共用；新增/删除屏蔽项会通过 usePreferences 的 version 触发所在页列表重取。
 */
export default function PreferencesPanel() {
  const { t } = useLanguage();
  const { toast } = useToast();
  const { items, add, remove } = usePreferences();
  const [activeType, setActiveType] = useState<PrefType>('subfield');
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);

  const activeItems = items.filter((p) => p.entity_type === activeType);
  const activeLabel = t(PREF_TYPES.find((x) => x.type === activeType)?.labelKey || 'pref.type.subfield');

  const handleAdd = async () => {
    const value = input.trim();
    if (!value) return;
    setBusy(true);
    try {
      await add(activeType, value);
      setInput('');
      toast(t('pref.hideMsg'), 'success');
    } catch {
      toast(t('pref.hideFailed'), 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (value: string) => {
    try {
      await remove(activeType, value);
      toast(t('pref.unhideMsg'), 'success');
    } catch {
      toast(t('pref.unhideFailed'), 'error');
    }
  };

  return (
    <section className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6" id="hide">
      <div className="flex items-center gap-2 mb-3">
        <EyeOff className="w-5 h-5 text-red-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('pref.title')}</h2>
        <span className="text-xs text-gray-400">{t('pref.subtitle')}</span>
      </div>

      {/* 类型切换 */}
      <div className="flex flex-wrap gap-2 mb-4">
        {PREF_TYPES.map(({ type, labelKey }) => (
          <button
            key={type}
            onClick={() => setActiveType(type)}
            className={`px-3 py-1.5 rounded-full text-xs border transition-colors ${
              activeType === type
                ? 'bg-red-500 text-white border-red-500'
                : 'bg-gray-50 dark:bg-gray-700/50 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:border-red-300'
            }`}
          >
            {t(labelKey)}
          </button>
        ))}
      </div>

      {/* 已有屏蔽项 */}
      {activeItems.length === 0 ? (
        <p className="text-sm text-gray-400 mb-4">{t('pref.empty')}</p>
      ) : (
        <div className="flex flex-wrap gap-2 mb-4">
          {activeItems.map((p) => (
            <span
              key={`${p.entity_type}:${p.entity_value}`}
              className="inline-flex items-center gap-1.5 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-xs px-2.5 py-1 rounded-full border border-red-200 dark:border-red-800"
            >
              <span className="max-w-[180px] truncate">{p.entity_value}</span>
              <button
                onClick={() => handleRemove(p.entity_value)}
                className="hover:bg-red-100 dark:hover:bg-red-900/50 rounded-full p-0.5"
                title={t('pref.remove')}
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* 手动新增 */}
      <div className="flex items-center gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleAdd(); }}
          placeholder={t('pref.addPlaceholder', { type: activeLabel })}
          className="flex-1 min-w-0 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 text-sm outline-none focus:ring-2 focus:ring-red-400 focus:border-transparent"
        />
        <button
          onClick={handleAdd}
          disabled={busy || !input.trim()}
          className="flex items-center gap-1 px-3 py-2 rounded-lg bg-red-500 text-white text-sm disabled:opacity-50 hover:bg-red-600 transition-colors"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          {t('pref.add')}
        </button>
      </div>
    </section>
  );
}
