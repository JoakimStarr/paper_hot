'use client';

import React, { useState, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { FileText, Loader2, Sparkles, Building2, Download, BookMarked, RefreshCw } from 'lucide-react';
import { workbenchApi, producerApi } from '@/lib/api';
import { downloadTextFile, downloadAsWord } from '@/lib/utils';
import type { StepProps } from './types';

const MarkdownRenderer = dynamic(() => import('@/components/MarkdownRenderer'), {
  ssr: false,
  loading: () => <div className="h-16 flex items-center justify-center text-gray-400 text-sm animate-pulse">加载中...</div>,
});

export default function Step5Writing({ project, onPatch, onRefresh, runAi }: StepProps) {
  const [journalBusy, setJournalBusy] = useState(false);
  const [proposalBusy, setProposalBusy] = useState(false);

  const aiRunning = project.ai_pending === 'literature_review';
  const papers = project.papers || [];

  const citations = useMemo(() => {
    const map: Record<number, { id: string; title?: string }> = {};
    papers.forEach((p, i) => { if (p.paper_id) map[i + 1] = { id: p.paper_id, title: p.title }; });
    return map;
  }, [papers]);

  const exportReview = (fmt: 'md' | 'doc') => {
    const content = project.literature_review || '';
    if (!content) return;
    const title = project.title || '文献综述';
    if (fmt === 'md') {
      downloadTextFile(`${title}_文献综述.md`, content, 'text/markdown;charset=utf-8');
    } else {
      downloadAsWord(`${title}_文献综述.doc`, title, content);
    }
  };

  const exportProposal = () => {
    if (!project.proposal) return;
    downloadTextFile(`${project.title}_立项书.md`, project.proposal, 'text/markdown;charset=utf-8');
  };

  const regenerateProposal = async () => {
    setProposalBusy(true);
    try {
      const res = await workbenchApi.generateProposal(project.id, project.validation_report || undefined);
      await onPatch({ proposal: res.proposal });
    } catch { /* ignore */ }
    finally { setProposalBusy(false); }
  };

  const suggestJournal = async () => {
    setJournalBusy(true);
    try {
      const res = await workbenchApi.suggestJournal(project.id);
      await onRefresh();
      if (!res.ai_used && res.suggestions.length > 0) {
        // 规则兜底时后端已存 journal_advice；无需额外处理
      }
    } catch { /* ignore */ }
    finally { setJournalBusy(false); }
  };

  const exportCitations = async (fmt: 'gbt7714' | 'bibtex') => {
    const snapshots = papers.map((p) => ({
      title: p.title,
      journal_name: p.journal,
      authors: p.authors || [],
      published_at: p.published_at,
    }));
    try {
      const res = await producerApi.exportCitations(snapshots, fmt);
      const text = res.citations.join('\n\n');
      const ext = fmt === 'bibtex' ? 'bib' : 'md';
      downloadTextFile(`${project.title}_参考文献.${ext}`, text, 'text/plain;charset=utf-8');
    } catch { /* ignore */ }
  };

  const exportAll = () => {
    const parts: string[] = [];
    parts.push(`# ${project.title}\n`);
    if (project.literature_review) {
      parts.push(`# 文献综述\n\n${project.literature_review}\n`);
    }
    if (project.proposal) {
      parts.push(`\n# 选题立项书\n\n${project.proposal}\n`);
    }
    if (project.journal_advice) {
      parts.push(`\n# 投稿期刊适配建议\n\n${project.journal_advice}\n`);
    }
    if (parts.length === 1) return;
    downloadTextFile(`${project.title}_研究资料包.md`, parts.join('\n---\n'), 'text/markdown;charset=utf-8');
  };

  return (
    <div className="space-y-5">
      {/* 综述 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-purple-200 dark:border-purple-800 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-gray-900 dark:text-white">
              <BookMarked className="w-4 h-4 text-purple-600" /> 文献综述
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">基于项目文献集生成结构化综述（研究脉络/方法演进/争议/空白）</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => runAi('literature_review')}
              disabled={aiRunning || papers.length === 0}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-xs rounded-lg transition-colors"
            >
              {aiRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              {project.literature_review ? '重新生成' : '生成综述'}
            </button>
            {project.literature_review && (
              <>
                <button onClick={() => exportReview('md')} className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                  <Download className="w-3.5 h-3.5" /> Markdown
                </button>
                <button onClick={() => exportReview('doc')} className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                  <FileText className="w-3.5 h-3.5" /> Word
                </button>
              </>
            )}
          </div>
        </div>
        {aiRunning && (
          <div className="flex items-center justify-center gap-2 text-sm text-purple-600 dark:text-purple-400 py-6">
            <Loader2 className="w-5 h-5 animate-spin" /> AI 正在生成综述（约 1 分钟）…
          </div>
        )}
        {!aiRunning && project.literature_review && (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <MarkdownRenderer content={project.literature_review} citations={citations} />
          </div>
        )}
        {!aiRunning && !project.literature_review && (
          <p className="text-xs text-gray-400">点击「生成综述」，AI 将基于项目文献集撰写。文献集为空时可先到第 3 步添加。</p>
        )}
      </div>

      {/* 立项书 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-green-200 dark:border-green-800 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-gray-900 dark:text-white">
              <FileText className="w-4 h-4 text-green-600" /> 选题立项书
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">研究问题/数据来源建议/方法论/研究步骤/预期贡献</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={regenerateProposal}
              disabled={proposalBusy}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 disabled:opacity-50 transition-colors"
            >
              {proposalBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
              重新生成
            </button>
            {project.proposal && (
              <button onClick={exportProposal} className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                <Download className="w-3.5 h-3.5" /> 下载
              </button>
            )}
          </div>
        </div>
        {project.proposal ? (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <MarkdownRenderer content={project.proposal} />
          </div>
        ) : (
          <p className="text-xs text-gray-400">回到第 2 步「选题验证」，验证完成后会自动生成立项书。</p>
        )}
      </div>

      {/* 期刊适配 + 引用 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-blue-200 dark:border-blue-800 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-gray-900 dark:text-white">
              <Building2 className="w-4 h-4 text-blue-600" /> 投稿期刊适配
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">依据论文库期刊分布 + 期刊画像推荐 2-3 个投稿目标</p>
          </div>
          <button
            onClick={suggestJournal}
            disabled={journalBusy}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
          >
            {journalBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Building2 className="w-4 h-4" />}
            {project.journal_advice ? '重新适配' : '获取期刊建议'}
          </button>
        </div>
        {project.journal_advice ? (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <MarkdownRenderer content={project.journal_advice} />
          </div>
        ) : (
          <p className="text-xs text-gray-400">生成综述后获取期刊建议，推荐会更贴合。</p>
        )}

        {/* 引用导出 */}
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <h3 className="text-xs font-semibold text-gray-600 dark:text-gray-300 mb-2">引用导出（{papers.length} 篇）</h3>
          <div className="flex gap-2">
            <button
              onClick={() => exportCitations('gbt7714')}
              disabled={papers.length === 0}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700/50 disabled:opacity-50 transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> GB/T 7714
            </button>
            <button
              onClick={() => exportCitations('bibtex')}
              disabled={papers.length === 0}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700/50 disabled:opacity-50 transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> BibTeX
            </button>
            <button
              onClick={exportAll}
              disabled={!project.literature_review && !project.proposal && !project.journal_advice}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white rounded-md transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> 打包导出全部
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
