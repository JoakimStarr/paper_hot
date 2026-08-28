'use client';

import React, { useState } from 'react';
import { Database, Loader2, Sparkles, Save, Check } from 'lucide-react';
import type { DataInsights } from '@/types/paper';
import type { StepProps } from './types';

export default function Step4Data({ project, onPatch, runAi }: StepProps) {
  const [myNotes, setMyNotes] = useState(project.data_insights?.my_notes || '');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const aiRunning = project.ai_pending === 'data_insights';
  const insights: DataInsights | null = project.data_insights || null;
  const hasAi = !!(insights && (insights.data_sources?.length || insights.methods?.length || insights.advice));

  const saveNotes = async () => {
    setSaving(true);
    const base = (insights || {}) as DataInsights;
    await onPatch({ data_insights: { ...base, my_notes: myNotes } });
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-5">
      {/* AI 数据线索 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-purple-200 dark:border-purple-800 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-gray-900 dark:text-white">
              <Database className="w-4 h-4 text-blue-600" /> 数据与方法线索
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              从项目文献集提取已有研究用的数据来源与识别策略，并给数据可得性建议
            </p>
          </div>
          <button
            onClick={() => runAi('data_insights')}
            disabled={aiRunning || (project.papers?.length || 0) === 0}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
          >
            {aiRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            {hasAi ? '重新提取' : '提取线索'}
          </button>
        </div>

        {aiRunning && (
          <div className="flex items-center justify-center gap-2 text-sm text-purple-600 dark:text-purple-400 py-6">
            <Loader2 className="w-5 h-5 animate-spin" /> AI 正在提取数据与方法线索…
          </div>
        )}

        {!aiRunning && hasAi && insights && (
          <div className="space-y-4">
            {insights.data_sources && insights.data_sources.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-600 dark:text-gray-300 mb-2">数据来源</h3>
                <ul className="space-y-1.5">
                  {insights.data_sources.map((d, i) => (
                    <li key={i} className="text-xs bg-gray-50 dark:bg-gray-700/40 rounded-md px-3 py-2">
                      <span className="font-medium text-gray-800 dark:text-gray-200">{d.name}</span>
                      {d.papers?.length > 0 && (
                        <span className="text-gray-400 ml-2">用于 [{d.papers.join('][')}]</span>
                      )}
                      {d.usage && <span className="block text-gray-500 mt-0.5">{d.usage}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {insights.methods && insights.methods.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-600 dark:text-gray-300 mb-2">研究方法</h3>
                <ul className="space-y-1.5">
                  {insights.methods.map((m, i) => (
                    <li key={i} className="text-xs bg-gray-50 dark:bg-gray-700/40 rounded-md px-3 py-2">
                      <span className="font-medium text-gray-800 dark:text-gray-200">{m.name}</span>
                      {m.papers?.length > 0 && <span className="text-gray-400 ml-2">用于 [{m.papers.join('][')}]</span>}
                      {m.note && <span className="block text-gray-500 mt-0.5">{m.note}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {insights.advice && (
              <div>
                <h3 className="text-xs font-semibold text-gray-600 dark:text-gray-300 mb-2">数据可得性建议</h3>
                <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800/50 rounded-md px-3 py-2">
                  {insights.advice}
                </p>
              </div>
            )}
          </div>
        )}
        {!aiRunning && !hasAi && (
          <p className="text-xs text-gray-400">先在「文献管理」添加论文（或第 2 步验证召回），再提取数据与方法线索。</p>
        )}
      </div>

      {/* 手动补充 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">我的数据与补充</h2>
          <button
            onClick={saveNotes}
            disabled={saving}
            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white rounded-md transition-colors"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : saved ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
            {saved ? '已保存' : '保存'}
          </button>
        </div>
        <p className="text-xs text-gray-400 mb-2">记录你自己已获得/计划申请的数据，作为项目的一部分沉淀下来</p>
        <textarea
          value={myNotes}
          onChange={(e) => setMyNotes(e.target.value)}
          rows={4}
          placeholder="例：已获取某省中小企业数据库 2015-2024；计划申请上市公司专利数据…"
          className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>
    </div>
  );
}
