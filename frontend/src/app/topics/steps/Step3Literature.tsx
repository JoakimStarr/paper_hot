'use client';

import React, { useState } from 'react';
import dynamic from 'next/dynamic';
import { BookOpen, Loader2, Plus, Trash2, Search, Sparkles, Download, Check } from 'lucide-react';
import { workbenchApi, producerApi } from '@/lib/api';
import { downloadTextFile } from '@/lib/utils';
import type { ProjectPaper, ProjectSearchPaper } from '@/types/paper';
import type { StepProps } from './types';

const MarkdownRenderer = dynamic(() => import('@/components/MarkdownRenderer'), {
  ssr: false,
  loading: () => <div className="h-16 flex items-center justify-center text-gray-400 text-sm animate-pulse">加载中...</div>,
});

const STATUS_LABELS: Record<string, string> = { to_read: '待读', reading: '精读中', read: '已读' };
const STATUS_STYLE: Record<string, string> = {
  to_read: 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300',
  reading: 'bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400',
  read: 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400',
};

export default function Step3Literature({ project, onPatch, runAi, onRefresh }: StepProps) {
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [candidates, setCandidates] = useState<ProjectSearchPaper[]>([]);
  const [searchMode, setSearchMode] = useState('');
  const [addingId, setAddingId] = useState<string | null>(null);
  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({});

  const aiRunning = project.ai_pending === 'literature_review';
  const papers = project.papers || [];

  const citations = React.useMemo(() => {
    const map: Record<number, { id: string; title?: string }> = {};
    papers.forEach((p, i) => { if (p.paper_id) map[i + 1] = { id: p.paper_id, title: p.title }; });
    return map;
  }, [papers]);

  const doSearch = async () => {
    const q = query.trim();
    if (!q || searching) return;
    setSearching(true);
    try {
      const res = await workbenchApi.searchProjectPapers(project.id, q, 10);
      setCandidates(res.papers || []);
      setSearchMode(res.mode || '');
    } catch { /* ignore */ }
    finally { setSearching(false); }
  };

  const addPaper = async (p: ProjectSearchPaper) => {
    setAddingId(p.id);
    try {
      await workbenchApi.addProjectPaper(project.id, p.id, p.similarity);
      await onRefresh();
      setCandidates((prev) => prev.map((x) => (x.id === p.id ? { ...x, in_project: true } : x)));
    } catch { /* 已存在等错误忽略 */ }
    finally { setAddingId(null); }
  };

  const setStatus = async (p: ProjectPaper, status: string) => {
    await workbenchApi.updateProjectPaper(project.id, p.paper_id, { read_status: status as ProjectPaper['read_status'] });
    await onRefresh();
  };

  const saveNote = async (p: ProjectPaper) => {
    await workbenchApi.updateProjectPaper(project.id, p.paper_id, { note: noteDrafts[p.paper_id] || '' });
    await onRefresh();
  };

  const removePaper = async (p: ProjectPaper) => {
    await workbenchApi.deleteProjectPaper(project.id, p.paper_id);
    await onRefresh();
  };

  const exportCitations = async () => {
    const snapshots = papers.map((p) => ({
      title: p.title,
      journal_name: p.journal,
      authors: p.authors || [],
      published_at: p.published_at,
    }));
    try {
      const res = await producerApi.exportCitations(snapshots, 'gbt7714');
      const text = res.citations.join('\n');
      downloadTextFile(`${project.title}_参考文献_GB7714.md`, text, 'text/plain;charset=utf-8');
    } catch { /* ignore */ }
  };

  return (
    <div className="space-y-5">
      {/* 检索添加 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
        <h2 className="flex items-center gap-1.5 text-base font-semibold text-gray-900 dark:text-white mb-3">
          <BookOpen className="w-4 h-4 text-green-600" /> 文献管理
          <span className="text-xs font-normal text-gray-400">{papers.length} 篇</span>
        </h2>
        <div className="flex gap-2 mb-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') doSearch(); }}
            placeholder="检索论文库，加入文献集（如：融资约束 数字金融）"
            className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-green-500"
          />
          <button
            onClick={doSearch}
            disabled={searching || !query.trim()}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors shrink-0"
          >
            {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            检索
          </button>
        </div>

        {candidates.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs text-gray-400">{searchMode === 'embedding+rerank' ? '语义检索+重排' : '语义检索'} 候选 {candidates.length} 条</div>
            {candidates.map((c) => (
              <div key={c.id} className="flex items-center justify-between gap-3 px-3 py-2 bg-gray-50 dark:bg-gray-700/40 border border-gray-200 dark:border-gray-600 rounded-md">
                <a href={`/paper/${c.id}`} target="_blank" rel="noopener noreferrer" className="flex-1 min-w-0">
                  <div className="text-xs text-gray-700 dark:text-gray-300 truncate">{c.title}</div>
                  <div className="text-[11px] text-gray-400 truncate">
                    {c.journal || c.source || ''}{c.published_at ? ` · ${c.published_at}` : ''}
                    {c.similarity != null ? ` · ${(c.similarity * 100).toFixed(0)}%` : ''}
                  </div>
                </a>
                <button
                  onClick={() => addPaper(c)}
                  disabled={c.in_project || addingId === c.id}
                  className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-md shrink-0 transition-colors disabled:opacity-50 disabled:cursor-not-allowed bg-primary-600 hover:bg-primary-700 text-white"
                >
                  {c.in_project ? <><Check className="w-3 h-3" /> 已在库</> : addingId === c.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <><Plus className="w-3 h-3" /> 加入</>}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 文献集列表 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">项目文献集</h3>
          <div className="flex gap-2">
            <button
              onClick={exportCitations}
              disabled={papers.length === 0}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700/50 disabled:opacity-50 transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> 导出引用
            </button>
            <button
              onClick={() => runAi('literature_review')}
              disabled={aiRunning || papers.length === 0}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-md transition-colors"
            >
              {aiRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              {project.literature_review ? '重新生成' : '生成文献脉络'}
            </button>
          </div>
        </div>

        {papers.length === 0 ? (
          <p className="text-xs text-gray-400 py-4">文献集为空。用上方搜索加入论文，或回到第 2 步验证召回。</p>
        ) : (
          <div className="space-y-2">
            {papers.map((p, i) => (
              <div key={p.paper_id} className="border border-gray-100 dark:border-gray-700 rounded-lg p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-gray-400 font-mono shrink-0">[{i + 1}]</span>
                      <a href={`/paper/${p.paper_id}`} target="_blank" rel="noopener noreferrer" className="text-sm text-gray-800 dark:text-gray-200 hover:text-primary-600 truncate">
                        {p.title}
                      </a>
                    </div>
                    <div className="text-[11px] text-gray-400 mt-0.5">
                      {p.journal || ''}{p.published_at ? ` · ${p.published_at}` : ''}
                      {p.similarity != null ? ` · 相似度 ${(p.similarity * 100).toFixed(0)}%` : ''}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <select
                      value={p.read_status}
                      onChange={(e) => setStatus(p, e.target.value)}
                      className={`text-[11px] px-2 py-1 rounded-md border border-transparent outline-none cursor-pointer ${STATUS_STYLE[p.read_status] || STATUS_STYLE.to_read}`}
                    >
                      <option value="to_read">待读</option>
                      <option value="reading">精读中</option>
                      <option value="read">已读</option>
                    </select>
                    <button onClick={() => removePaper(p)} className="p-1 text-gray-300 hover:text-red-500 transition-colors" title="移除">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <input
                    value={noteDrafts[p.paper_id] ?? p.note ?? ''}
                    onChange={(e) => setNoteDrafts((prev) => ({ ...prev, [p.paper_id]: e.target.value }))}
                    onBlur={() => saveNote(p)}
                    onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                    placeholder="笔记（核心结论、可借鉴的方法/数据）…"
                    className="flex-1 px-2.5 py-1 text-xs border border-gray-200 dark:border-gray-700 rounded-md bg-gray-50 dark:bg-gray-700/40 text-gray-700 dark:text-gray-300 placeholder-gray-400 outline-none focus:ring-1 focus:ring-green-400"
                  />
                </div>
              </div>
            ))}
          </div>
        )}

        {aiRunning && (
          <div className="mt-4 flex items-center justify-center gap-2 text-sm text-purple-600 dark:text-purple-400 py-4">
            <Loader2 className="w-5 h-5 animate-spin" /> AI 正在生成文献脉络…
          </div>
        )}
        {!aiRunning && project.literature_review && (
          <div className="mt-4 prose prose-sm dark:prose-invert max-w-none">
            <MarkdownRenderer content={project.literature_review} citations={citations} />
          </div>
        )}
      </div>
    </div>
  );
}
