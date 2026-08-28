'use client';

import { AlertTriangle, Loader2 } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';

interface ConfirmModalProps {
  open: boolean;
  title: string;
  description?: string;
  /** 危险操作确认按钮为红色 */
  danger?: boolean;
  /** 确认中：按钮显示 loading 并禁用 */
  confirming?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmModal({
  open,
  title,
  description,
  danger,
  confirming,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  const { t } = useLanguage();
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-black/50" onClick={confirming ? undefined : onCancel} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-200 dark:border-gray-700 max-w-sm w-full p-5">
        <div className="flex items-start gap-3">
          <span className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center ${danger ? 'bg-red-100 dark:bg-red-900/40 text-red-600' : 'bg-amber-100 dark:bg-amber-900/40 text-amber-600'}`}>
            <AlertTriangle className="w-5 h-5" />
          </span>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-gray-900 dark:text-white">{title}</h3>
            {description && (
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400 whitespace-pre-line">{description}</p>
            )}
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={confirming}
            className="px-4 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 transition-colors"
          >
            {t('common.cancel')}
          </button>
          <button
            onClick={onConfirm}
            disabled={confirming}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg text-white disabled:opacity-50 transition-colors ${
              danger ? 'bg-red-600 hover:bg-red-700' : 'bg-primary-600 hover:bg-primary-700'
            }`}
          >
            {confirming && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {t('common.confirm')}
          </button>
        </div>
      </div>
    </div>
  );
}
