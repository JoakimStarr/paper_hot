'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'next/navigation';
import Layout from '@/components/Layout';
import { papersApi, API_BASE_URL } from '@/lib/api';
import { PaperDetailResponse } from '@/types/paper';
import { Loader2, ExternalLink, Calendar, Award, TrendingUp, ArrowLeft, AlertCircle, Sparkles, Send, Bot } from 'lucide-react';
import Link from 'next/link';
import { format } from 'date-fns';
import { useLanguage } from '@/contexts/LanguageContext';

const topicColors: Record<string, string> = {
  LLM: 'bg-purple-100 text-purple-800',
  Agent: 'bg-green-100 text-green-800',
  CV: 'bg-blue-100 text-blue-800',
  RL: 'bg-orange-100 text-orange-800',
  Multimodal: 'bg-pink-100 text-pink-800',
  NLP: 'bg-yellow-100 text-yellow-800',
  Generative: 'bg-indigo-100 text-indigo-800',
  Other: 'bg-gray-100 text-gray-800',
};

function getIssuePeriod(doi: string | null, publishedAt: string | null): string {
  if (doi) {
    const mm = doi.match(/\.(\d{4})\.(\d{2})\.(\d+)$/);
    if (mm) {
      return `${mm[1]}年 第${parseInt(mm[2], 10)}期`;
    }
    const ymd = doi.match(/\.(\d{4})(\d{2})(\d{2})\.(\d+)$/);
    if (ymd) {
      return `${ymd[1]}年 第${parseInt(ymd[2], 10)}期`;
    }
    const fy = doi.match(/f\.(\d{4})\.\d+$/);
    if (fy) {
      return `${fy[1]}年`;
    }
  }
  if (publishedAt) {
    return `${new Date(publishedAt).getFullYear()}年`;
  }
  return '';
}

export default function PaperDetailPage() {
  const { t } = useLanguage();
  const params = useParams();
  const [paper, setPaper] = useState<PaperDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [aiAnalysis, setAiAnalysis] = useState<string | null>(null);
  const [aiAnalyzing, setAiAnalyzing] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const [chatMessages, setChatMessages] = useState<Array<{ role: string; content: string }>>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatStreaming, setChatStreaming] = useState(false);
  const [streamContent, setStreamContent] = useState('');
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (params.id) {
      fetchPaper();
    }
  }, [params.id]);

  useEffect(() => {
    if (paper?.id) {
      loadLatestAnalysis();
    }
  }, [paper?.id]);

  const loadLatestAnalysis = async () => {
    try {
      const result = await papersApi.getLatestAnalysis(paper!.id);
      if (result.analysis) {
        setAiAnalysis(result.analysis);
      }
    } catch {}
  };

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [streamContent, chatMessages]);

  const fetchPaper = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await papersApi.getPaperById(params.id as string);
      setPaper(response);
    } catch (error: any) {
      console.error('Error fetching paper:', error);
      const errMsg = error.response?.data?.detail || error.message || '加载论文详情失败';
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  const analyzePaper = async () => {
    if (!params.id) return;
    setAiAnalyzing(true);
    setAiError(null);
    setAiAnalysis(null);
    setChatMessages([]);
    setStreamContent('');
    try {
      const result = await papersApi.analyzePaper(params.id as string);
      setAiAnalysis(result.analysis);
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || 'AI analysis failed';
      setAiError(msg);
    } finally {
      setAiAnalyzing(false);
    }
  };

  const handleChatSubmit = async () => {
    if (!chatInput.trim() || !paper) return;

    const userMsg = { role: 'user', content: chatInput.trim() };
    const allMessages = [...chatMessages, userMsg];
    setChatMessages(allMessages);
    setChatInput('');
    setChatStreaming(true);
    setStreamContent('');

    try {
      const response = await fetch(`${API_BASE_URL}/papers/${paper.id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: allMessages }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Request failed' }));
        setChatMessages(m => [...m, { role: 'assistant', content: `[Error] ${err.detail}` }]);
        setChatStreaming(false);
        return;
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullContent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.done) {
                setChatMessages(m => [...m, { role: 'assistant', content: fullContent }]);
                setStreamContent('');
              } else if (data.content) {
                fullContent += data.content;
                setStreamContent(fullContent);
              }
            } catch {}
          }
        }
      }
    } catch (e: any) {
      setChatMessages(m => [...m, { role: 'assistant', content: `[Error] ${e.message}` }]);
    } finally {
      setChatStreaming(false);
    }
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <div className="text-center py-12">
          <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <p className="text-red-600 font-medium mb-2">加载失败</p>
          <p className="text-gray-500 text-sm mb-4">{error}</p>
          <Link href="/" className="text-primary-600 hover:underline mt-4 inline-block">
            {t('nav.home')}
          </Link>
        </div>
      </Layout>
    );
  }

  if (!paper) {
    return (
      <Layout>
        <div className="text-center py-12">
          <p className="text-gray-600">{t('home.noPapers')}</p>
          <Link href="/" className="text-primary-600 hover:underline mt-4 inline-block">
            {t('nav.home')}
          </Link>
        </div>
      </Layout>
    );
  }

  const score = paper.scores?.final_score || 0;
  const shouldReadScore = paper.should_read_score || score;

  return (
    <Layout>
      <div className="mb-6">
        <Link href="/" className="flex items-center gap-2 text-gray-600 hover:text-primary-600 transition-colors">
          <ArrowLeft className="w-5 h-5" />
          <span>{t('home.previous')}</span>
        </Link>
      </div>

      <div className="bg-white rounded-lg shadow-md p-8 mb-6">
        <div className="flex justify-between items-start mb-4">
          <h1 className="text-2xl font-bold text-gray-900 flex-1">
            {paper.title}
          </h1>
          <a
            href={paper.url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-4 text-primary-600 hover:text-primary-700"
          >
            <ExternalLink className="w-6 h-6" />
          </a>
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          {paper.features?.topic && (
            <span className={`text-sm font-medium px-3 py-1 rounded ${topicColors[paper.features.topic] || topicColors.Other}`}>
              {paper.features.topic}
            </span>
          )}
          {paper.keywords_cn?.slice(0, 5).map((keyword, index) => (
            <span key={index} className="bg-gray-100 text-gray-700 text-sm px-3 py-1 rounded">
              {keyword}
            </span>
          ))}
        </div>

        <div className="flex items-center gap-6 text-sm text-gray-600 mb-6">
          <span className="flex items-center gap-1">
            <Calendar className="w-4 h-4" />
            {getIssuePeriod(paper.doi, paper.published_at) || 'Unknown'}
          </span>
          {paper.discipline && (
            <span className="bg-purple-50 text-purple-700 px-3 py-1 rounded">
              {paper.discipline}
            </span>
          )}
          <span className="bg-gray-100 px-3 py-1 rounded">
            {paper.source}
          </span>
          {paper.venue && (
            <span className="bg-primary-50 text-primary-700 px-3 py-1 rounded">
              {paper.venue}
            </span>
          )}
          {paper.journal_name && (
            <span className="bg-blue-50 text-blue-700 px-3 py-1 rounded">
              {paper.journal_name}
            </span>
          )}
        </div>

        {paper.doi && (
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-2">DOI</h2>
            <a
              href={paper.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 hover:underline text-sm break-all"
            >
              {paper.doi} &rarr;
            </a>
          </div>
        )}

        {paper.authors && paper.authors.length > 0 && (
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-2">{t('paper.authors')}</h2>
            <div className="flex flex-wrap gap-2">
              {paper.authors.map((author, index) => (
                <span key={index} className="bg-gray-100 text-gray-700 text-sm px-3 py-1 rounded">
                  {author}
                </span>
              ))}
            </div>
          </div>
        )}

        {paper.keywords_cn && paper.keywords_cn.length > 0 && (
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-2">{t('paper.keywords')}</h2>
            <div className="flex flex-wrap gap-2">
              {paper.keywords_cn.map((keyword, index) => (
                <span key={index} className="bg-primary-100 text-primary-800 text-sm px-3 py-1 rounded-full">
                  {keyword}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">{t('home.subtitle')}</h2>
          <p className="text-gray-700 leading-relaxed">
            {paper.features?.summary || paper.abstract}
          </p>
        </div>

        <div className="border-t pt-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-green-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Recency Score</div>
              <div className="text-lg font-bold text-gray-900">
                {((paper.scores?.recency_score || 0) * 100).toFixed(0)}%
              </div>
            </div>
            <div className="bg-blue-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Venue Score</div>
              <div className="text-lg font-bold text-gray-900">
                {((paper.scores?.venue_score || 0) * 100).toFixed(0)}%
              </div>
            </div>
            <div className="bg-purple-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Trend Score</div>
              <div className="text-lg font-bold text-gray-900">
                {((paper.scores?.trend_score || 0) * 100).toFixed(0)}%
              </div>
            </div>
          </div>

          {paper.should_read_score && (
            <div className="mt-4 bg-yellow-50 border border-yellow-200 p-4 rounded-lg">
              <div className="flex items-center gap-2">
                <Award className="w-5 h-5 text-yellow-700" />
                <span className="font-semibold text-yellow-900">
                  {t('paper.shouldReadScore')}: {(shouldReadScore * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-sm text-yellow-800 mt-1">
                {shouldReadScore >= 0.7
                  ? t('paper.highlyRecommended')
                  : shouldReadScore >= 0.5
                  ? t('paper.worthReading')
                  : t('paper.considerReading')}
              </p>
            </div>
          )}
        </div>
      </div>

      {paper.similar_papers && paper.similar_papers.length > 0 && (
        <div className="bg-white rounded-lg shadow-md p-8 mb-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">{t('paper.similarPapers')}</h2>
          <div className="space-y-3">
            {paper.similar_papers.map((similar) => (
              <Link
                key={similar.id}
                href={`/paper/${similar.id}`}
                className="block border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <h3 className="font-semibold text-gray-900 mb-2">
                      {similar.title}
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {similar.topic && (
                        <span className={`text-xs font-medium px-2 py-0.5 rounded ${topicColors[similar.topic] || topicColors.Other}`}>
                          {similar.topic}
                        </span>
                      )}
                      {similar.keywords_cn?.slice(0, 5).map((keyword, index) => (
                        <span key={index} className="bg-gray-100 text-gray-600 text-xs px-2 py-0.5 rounded">
                          {keyword}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="text-sm text-gray-600 ml-4 shrink-0">
                    {(similar.similarity_score * 100).toFixed(0)}% similar
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg shadow-md p-8 mb-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary-600" />
            <h2 className="text-xl font-semibold text-gray-900">AI 智能分析</h2>
          </div>
          {aiAnalysis && !aiAnalyzing && (
            <button
              onClick={analyzePaper}
              className="text-sm text-primary-600 hover:underline"
            >
              重新分析
            </button>
          )}
        </div>

        {aiAnalyzing && (
          <div className="flex items-center gap-3 py-8 justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-primary-600" />
            <span className="text-gray-500">正在分析论文，请稍候...</span>
          </div>
        )}

        {aiError && !aiAnalyzing && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
            <p className="text-red-700 text-sm">{aiError}</p>
            <button
              onClick={analyzePaper}
              className="mt-2 text-sm text-primary-600 hover:underline"
            >
              重试
            </button>
          </div>
        )}

        {!aiAnalysis && !aiAnalyzing && !aiError && (
          <div className="text-center py-8">
            <Bot className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 text-sm mb-4">点击下方按钮，让 AI 帮你分析这篇论文</p>
            <button
              onClick={analyzePaper}
              className="bg-primary-600 text-white px-6 py-2.5 rounded-lg hover:bg-primary-700 text-sm font-medium"
            >
              <Sparkles className="w-4 h-4 inline mr-2" />
              开始 AI 分析
            </button>
          </div>
        )}

        {aiAnalysis && !aiAnalyzing && (
          <div className="prose prose-gray max-w-none text-sm leading-relaxed whitespace-pre-wrap">
            {aiAnalysis}
          </div>
        )}

        {aiAnalysis && !aiAnalyzing && (
          <>
            <div className="border-t mt-6 pt-6">
              <h3 className="text-base font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <Bot className="w-4 h-4 text-primary-600" />
                追问讨论
              </h3>

              <div className="space-y-4 mb-4 max-h-[400px] overflow-y-auto">
                {chatMessages.map((msg, i) => (
                  <div
                    key={i}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-lg px-4 py-2 text-sm ${
                        msg.role === 'user'
                          ? 'bg-primary-600 text-white'
                          : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>
                ))}

                {chatStreaming && streamContent && (
                  <div className="flex justify-start">
                    <div className="max-w-[80%] rounded-lg px-4 py-2 text-sm bg-gray-100 text-gray-800">
                      {streamContent}
                      <span className="inline-block w-1.5 h-4 bg-primary-600 ml-0.5 animate-pulse align-middle" />
                    </div>
                  </div>
                )}

                {chatStreaming && !streamContent && (
                  <div className="flex justify-start">
                    <div className="bg-gray-100 rounded-lg px-4 py-3">
                      <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                    </div>
                  </div>
                )}

                <div ref={chatEndRef} />
              </div>

              <div className="flex gap-2">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey && !chatStreaming) {
                      e.preventDefault();
                      handleChatSubmit();
                    }
                  }}
                  placeholder="针对这篇论文提问..."
                  disabled={chatStreaming}
                  className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-gray-50"
                />
                <button
                  onClick={handleChatSubmit}
                  disabled={chatStreaming || !chatInput.trim()}
                  className="bg-primary-600 text-white rounded-lg px-4 py-2 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </Layout>
  );
}