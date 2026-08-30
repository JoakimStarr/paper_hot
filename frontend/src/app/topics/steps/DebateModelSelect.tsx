'use client';

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { rememberModel } from '@/lib/api';

/**
 * 角色模型下拉（辩论/答辩共用）。
 * 每项含「默认（跟随全局设置）」；选择结果记忆到 localStorage（memKey）。
 */
export default function DebateModelSelect({ roleLabel, memKey, value, models, onChange }: {
  roleLabel: string;
  memKey: string;
  value: string;
  models: Array<{ id: string; label: string }>;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const pick = (v: string) => {
    rememberModel(memKey, v || null);
    onChange(v);
    setOpen(false);
  };
  return (
    <div className="relative inline-flex items-center gap-1.5">
      <span className="text-xs text-gray-400 shrink-0">{roleLabel}</span>
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors"
        title="选择该角色的模型（默认自动跟随全局设置）"
      >
        {value ? (models.find((m) => m.id === value)?.label || value) : '默认模型'}
        <ChevronDown className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg py-1 min-w-[200px] max-h-72 overflow-y-auto">
          <button
            onClick={() => pick('')}
            className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${value === '' ? 'text-violet-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
          >
            默认（跟随全局设置）
          </button>
          {models.map((m) => (
            <button
              key={m.id}
              onClick={() => pick(m.id)}
              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${value === m.id ? 'text-violet-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
            >
              {m.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
