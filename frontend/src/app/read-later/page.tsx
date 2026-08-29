'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import { Clock, Loader2, Check, X } from 'lucide-react';
import Link from 'next/link';
import { useLanguage } from '@/contexts/LanguageContext';
import { usePageTitle } from '@/lib/usePageTitle';
import { useToast } from '@/components/Toast';
import { personalApi } from '@/lib/api';
import { downloadTextFile } from '@/lib/utils';
import { producerApi } from '@/lib/api';
import type { PaperCard as PaperCardType } from '@/types/paper';

/** 稍后读页面：队列完整视图（工作台仅展示入口与最近队列）。 */
export default function ReadLaterPage() {
  const { t } = useLanguage();
  usePageTitle(t('nav.readLater'));
  const { toast } = useToast();
  const [papers, setPapers] = useState<PaperCardType[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await personalApi.getReadLaterPapers();
      setPapers(res.papers || []);
    } catch {
      setPapers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const done = async (pid: string) => {
    setBusyId(pid);
    try {
      await personalApi.recordReading(pid);
      await personalApi.toggleReadLater(pid); // 队列中 -> 移出
      toast(t('dash.readLaterDoneMsg'), 'success');
      await load();
    } catch {
      toast(t('pref.hideFailed'), 'error');
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (pid: string) => {
    setBusyId(pid);
    try {
      await personalApi.toggleReadLater(pid);
      await load();
    } catch {
      toast(t('pref.hideFailed'), 'error');
    } finally {
      setBusyId(null);
    }
  };

  /** 队列引用导出（GB/T 7714），供打印/写作时直接使用 */
  const exportCitations = async () => {
    if (papers.length === 0) return;
    try {
      const snapshots = papers.map((p) => ({
        title: p.title,
        journal_name: p.journal_name,
        authors: p.authors || [],
        published_at: p.published_at,
      }));
      const res = await producerApi.exportCitations(snapshots, 'gbt7714');
      downloadTextFile(`稍后读_参考文献.md`, res.citations.join('\n\n'), 'text/plain;charset=utf-8');
    } catch {
      toast(t('pref.hideFailed'), 'error');
    }
  };

  return (
    <Layout>
      <div className="mb-5">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Clock className="w-6 h-6 text-amber-500" />
          稍后读
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          论文卡片上的时钟图标即可加入队列；读完点「标记已读」自动移出并计入阅读历史
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      ) : papers.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-10 text-center">
          <p className="text-sm text-gray-400 mb-2">{t('dash.readLaterEmpty')}</p>
          <Link href="/" className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
            去首页找论文 →
          </Link>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-gray-400">{t('dash.readLaterCount', { n: papers.length })}</span>
            <button
              onClick={exportCitations}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              导出引用（GB/T 7714）
            </button>
          </div>
          <div className="space-y-4">
            {papers.map((p) => (
              <div key={p.id} className="relative">
                <PaperCard paper={p} surface="read_later" />
                {/* 队列操作条 */}
                <div className="absolute bottom-3 right-3 flex items-center gap-2">
                  <button
                    onClick={() => done(p.id)}
                    disabled={busyId === p.id}
                    className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300 bg-white/80 dark:bg-gray-800/80 hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors disabled:opacity-50"
                    title={t('dash.readLaterDone')}
                  >
                    {busyId === p.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                    标记已读
                  </button>
                  <button
                    onClick={() => remove(p.id)}
                    disabled={busyId === p.id}
                    className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border border-gray-200 dark:border-gray-700 text-gray-400 bg-white/80 dark:bg-gray-800/80 hover:text-red-500 transition-colors disabled:opacity-50"
                    title={t('dash.readLaterRemove')}
                  >
                    <X className="w-3 h-3" /> 移出
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </Layout>
  );
}
