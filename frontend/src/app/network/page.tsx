'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import Layout from '@/components/Layout';
import SkeletonCard from '@/components/SkeletonCard';
import { papersApi } from '@/lib/api';
import KeywordContextActions from '@/components/KeywordContextActions';
import EntryCard from '@/components/EntryCard';
import { NetworkData, NetworkNode } from '@/types/paper';
import { Loader2, Hash, ChevronRight, ExternalLink, Map as MapIcon, Target, TrendingUp, Crosshair } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import type { KeywordMapResponse } from '@/lib/api';

const NetworkGraph = dynamic(() => import('./NetworkGraph'), { ssr: false });
const ClusterMap = dynamic(() => import('./ClusterMap'), { ssr: false });
const GapsPanel = dynamic(() => import('./GapsPanel'), { ssr: false });

type TabType = 'clusters' | 'keywords' | 'gaps';

interface ConnectedNode {
  id: string;
  name: string;
  group: string;
  linkValue: number;
  count: number;
}

function getLinkNodeId(node: string | { id?: string }): string {
  if (typeof node === 'string') return node;
  if (node && 'id' in node && typeof node.id === 'string') return node.id;
  return String(node);
}

export default function NetworkPage() {
  const { t } = useLanguage();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<TabType>('keywords');
  const [data, setData] = useState<NetworkData | null>(null);
  const [loading, setLoading] = useState(true);
  const [infoNode, setInfoNode] = useState<NetworkNode | null>(null);
  const [highlightedNodeId, setHighlightedNodeId] = useState<string | null>(null);
  const [linkedFilter, setLinkedFilter] = useState('');

  const fetchData = useCallback(async (tab: TabType) => {
    setLoading(true);
    setInfoNode(null);
    setHighlightedNodeId(null);
    try {
      const res = await papersApi.getKeywordNetwork();
      setData(res);
    } catch (error) {
      console.error('Error fetching network data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'keywords') fetchData(activeTab);
  }, [activeTab, fetchData]);

  const connectedNodes: ConnectedNode[] = useMemo(() => {
    if (!data || !highlightedNodeId) return [];
    const nodesMap = new Map<string, NetworkNode>();
    data.nodes.forEach(n => nodesMap.set(n.id, n));

    const connections = new Map<string, ConnectedNode>();
    data.links.forEach(link => {
      const sourceId = getLinkNodeId(link.source);
      const targetId = getLinkNodeId(link.target);

      let neighborId: string | null = null;
      if (sourceId === highlightedNodeId) neighborId = targetId;
      else if (targetId === highlightedNodeId) neighborId = sourceId;
      else return;

      if (!neighborId) return;

      const node = nodesMap.get(neighborId);
      if (!node) return;

      const existing = connections.get(neighborId);
      if (!existing || link.value > existing.linkValue) {
        connections.set(neighborId, {
          id: neighborId,
          name: node.name,
          group: node.group,
          linkValue: link.value,
          count: node.papers || node.count || 0,
        });
      }
    });

    return Array.from(connections.values())
      .sort((a, b) => b.linkValue - a.linkValue);
  }, [data, highlightedNodeId]);

  const handleNodeClick = useCallback((node: NetworkNode) => {
    if (!node.id) {
      setInfoNode(null);
      setHighlightedNodeId(null);
      setLinkedFilter('');
      return;
    }
    setInfoNode(node);
    setHighlightedNodeId(node.id);
    setLinkedFilter('');
  }, []);

  // —— 研究版图（P2-13a）：点关键词节点 -> 动态生成该词的研究版图 ——
  const [keywordMap, setKeywordMap] = useState<KeywordMapResponse | null>(null);
  const [mapLoading, setMapLoading] = useState(false);

  useEffect(() => {
    if (!infoNode || infoNode.group !== 'keyword' || !infoNode.name) {
      setKeywordMap(null);
      return;
    }
    let cancelled = false;
    setMapLoading(true);
    setKeywordMap(null);
    papersApi.getKeywordMap(infoNode.name)
      .then((res) => { if (!cancelled) setKeywordMap(res); })
      .catch(() => { if (!cancelled) setKeywordMap(null); })
      .finally(() => { if (!cancelled) setMapLoading(false); });
    return () => { cancelled = true; };
  }, [infoNode]);

  /** 一键转选题：把关键词带入选题验证器。 */
  const handleToTopic = (keyword: string) => {
    try {
      localStorage.setItem('pp_topic_prefill', keyword);
    } catch { /* ignore */ }
    router.push('/topics?tab=validator');
  };

  const handleConnectedNodeClick = (node: ConnectedNode) => {
    setInfoNode({
      id: node.id,
      name: node.name,
      group: node.group,
      count: node.count,
    });
    setHighlightedNodeId(node.id);
    setLinkedFilter('');
  };

  const handleNavigateToNode = (node: ConnectedNode) => {
    const searchField = node.group === 'keyword' ? 'keyword' : 'author';
    router.push(`/search?search=${encodeURIComponent(node.name)}&search_field=${searchField}`);
  };

  const handleClearHighlight = () => {
    setHighlightedNodeId(null);
    setInfoNode(null);
  };

  return (
    <Layout>
      <div className="mb-6 sm:mb-8">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white mb-2">
          {t('net.title')}
        </h1>
        <p className="text-sm sm:text-base text-gray-600 dark:text-gray-400">
          {t('net.subtitle')}
        </p>
      </div>

      <EntryCard
        href="/trends"
        icon={<TrendingUp className="w-5 h-5" />}
        title={t('net.entryTrendsTitle')}
        desc={t('net.entryTrendsDesc')}
        className="mb-4 sm:mb-6"
      />

      <div className="flex flex-col sm:flex-row gap-2 sm:gap-4 mb-4 sm:mb-6">
        <button
          onClick={() => setActiveTab('keywords')}
          className={`flex items-center justify-center gap-2 px-3 sm:px-4 py-2 sm:py-2.5 rounded-lg text-xs sm:text-sm font-medium transition-colors ${
            activeTab === 'keywords'
              ? 'bg-primary-600 text-white'
              : 'bg-white dark:bg-gray-800 border border-gray-300 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
          }`}
        >
          <Hash className="w-4 h-4" />
          {t('net.keywords')}
        </button>
        <button
          onClick={() => setActiveTab('clusters')}
          className={`flex items-center justify-center gap-2 px-3 sm:px-4 py-2 sm:py-2.5 rounded-lg text-xs sm:text-sm font-medium transition-colors ${
            activeTab === 'clusters'
              ? 'bg-primary-600 text-white'
              : 'bg-white dark:bg-gray-800 border border-gray-300 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
          }`}
        >
          <MapIcon className="w-4 h-4" />
          {t('net.clusters')}
        </button>
        <button
          onClick={() => setActiveTab('gaps')}
          className={`flex items-center justify-center gap-2 px-3 sm:px-4 py-2 sm:py-2.5 rounded-lg text-xs sm:text-sm font-medium transition-colors ${
            activeTab === 'gaps'
              ? 'bg-primary-600 text-white'
              : 'bg-white dark:bg-gray-800 border border-gray-300 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
          }`}
        >
          <Crosshair className="w-4 h-4" />
          {t('net.gaps')}
        </button>
      </div>

      {activeTab === 'clusters' ? (
        <ClusterMap />
      ) : activeTab === 'gaps' ? (
        <GapsPanel />
      ) : loading ? (
        <div className="grid grid-cols-1 gap-4 sm:gap-6">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : (
        <>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-3 sm:p-4 mb-4">
            <div className="flex items-center gap-2 flex-wrap">
              {highlightedNodeId && (
                <button
                  onClick={handleClearHighlight}
                  className="px-2 sm:px-3 py-1 sm:py-1.5 text-xs bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 rounded-md transition-colors text-gray-600 dark:text-gray-400"
                >
                  清除高亮
                </button>
              )}
              <span className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
                {data?.nodes.length || 0} · {data?.links.length || 0} — {t('net.zoomHint')}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 sm:gap-6">
            <div className="lg:col-span-3">
              <NetworkGraph
                data={data}
                highlightedNodeId={highlightedNodeId}
                onNodeClick={handleNodeClick}
              />
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-3 sm:p-4">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">{t('net.nodeDetail')}</h3>
              {infoNode ? (
                <div className="space-y-3 text-sm">
                  <div>
                    <span className="text-gray-400 block text-xs">名称</span>
                    <span className="text-gray-900 dark:text-white font-medium">{infoNode.name}</span>
                  </div>
                  <div>
                    <span className="text-gray-400 block text-xs">类型</span>
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700">
                      <Hash className="w-3 h-3" />
                      {t('common.keyword')}
                    </span>
                  </div>
                  {infoNode.count !== undefined && (
                    <div>
                      <span className="text-gray-400 block text-xs">出现次数</span>
                      <span className="text-gray-900 dark:text-white font-semibold text-base sm:text-lg">{infoNode.count}</span>
                    </div>
                  )}

                  {connectedNodes.length > 0 && (
                    <div className="pt-3 border-t border-gray-100 dark:border-gray-700">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-gray-400 block text-xs">
                          {t('net.linkedKeywords')} ({connectedNodes.length})
                        </span>
                      </div>
                      {/* 关联关键词筛选 */}
                      <input
                        type="text"
                        value={linkedFilter}
                        onChange={e => setLinkedFilter(e.target.value)}
                        placeholder="筛选关联关键词..."
                        className="w-full mb-2 px-3 py-1.5 border border-gray-200 dark:border-gray-600 rounded-md text-xs outline-none focus:ring-1 focus:ring-primary-500 bg-gray-50 dark:bg-gray-700/40"
                      />
                      <div className="space-y-1 max-h-48 sm:max-h-64 overflow-y-auto">
                        {(linkedFilter.trim()
                          ? connectedNodes.filter(n => n.name.toLowerCase().includes(linkedFilter.trim().toLowerCase()))
                          : connectedNodes
                        ).map(node => (
                          <div
                            key={node.id}
                            className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-left text-xs ${
                              highlightedNodeId === node.id ? 'bg-primary-50 dark:bg-primary-900/30 ring-1 ring-primary-200' : ''
                            }`}
                          >
                            <button
                              onClick={() => handleConnectedNodeClick(node)}
                              className="flex items-center gap-2 flex-1 min-w-0 hover:text-primary-600 transition-colors"
                              title="点击切换查看该节点"
                            >
                              <ChevronRight className="w-3 h-3 text-gray-300 flex-shrink-0" />
                              <span className="text-gray-700 dark:text-gray-300 truncate">{node.name}</span>
                            </button>
                            <button
                              onClick={() => handleNavigateToNode(node)}
                              className="flex-shrink-0 flex items-center gap-1 px-2 py-0.5 rounded-md bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 hover:bg-primary-100 dark:hover:bg-primary-900/50 transition-colors"
                              title="查看相关论文"
                            >
                              <ExternalLink className="w-3 h-3" />
                              相关论文
                            </button>
                            <span className="text-gray-400 flex-shrink-0">
                              {node.linkValue > 1 ? `${node.linkValue}次` : ''}
                            </span>
                          </div>
                        ))}
                        {linkedFilter.trim() && connectedNodes.filter(n => n.name.toLowerCase().includes(linkedFilter.trim().toLowerCase())).length === 0 && (
                          <div className="text-center py-3 text-gray-400 text-xs">未找到匹配的关联节点</div>
                        )}
                      </div>
                    </div>
                  )}

                  <div className="pt-3 border-t border-gray-100 dark:border-gray-700 mt-2">
                    <span className="text-gray-400 block text-xs mb-1.5">{t('net.contextActions')}</span>
                    <KeywordContextActions keyword={infoNode.name} />
                  </div>

                  <div className="pt-2 border-t border-gray-100 dark:border-gray-700 mt-2">
                    <span className="text-gray-400 block text-xs">提示</span>
                    <span className="text-gray-500 dark:text-gray-400 text-xs">
                      点击关联节点可切换查看。点击 <ExternalLink className="w-2.5 h-2.5 inline-block text-gray-400" /> 可跳转搜索相关论文。
                    </span>
                  </div>

                  {/* 研究版图（P2-13a）：查询驱动，点关键词即出 */}
                  {infoNode.group === 'keyword' && (
                    <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                      <h4 className="flex items-center gap-1.5 text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                        <MapIcon className="w-4 h-4 text-primary-500" />
                        研究版图
                        <button
                          onClick={() => handleToTopic(infoNode.name)}
                          className="ml-auto flex items-center gap-1 px-2.5 py-1 text-xs rounded-full bg-primary-600 text-white hover:bg-primary-700 transition-colors"
                          title={`把「${infoNode.name}」带入选题验证器`}
                        >
                          <Target className="w-3 h-3" />
                          转选题
                        </button>
                      </h4>

                      {mapLoading ? (
                        <div className="flex items-center gap-2 text-xs text-gray-400 py-2">
                          <Loader2 className="w-3.5 h-3.5 animate-spin" /> 正在生成研究版图…
                        </div>
                      ) : keywordMap ? (
                        <div className="space-y-3 text-xs">
                          <div className="flex items-center justify-between bg-gray-50 dark:bg-gray-700/40 rounded-md px-2.5 py-1.5">
                            <span className="text-gray-500">库内相关论文</span>
                            <span className="font-semibold text-gray-900 dark:text-white">{keywordMap.total_papers} 篇</span>
                          </div>

                          {/* 年度趋势迷你柱状 */}
                          {keywordMap.yearly_trend.length > 0 && (
                            <div>
                              <p className="text-gray-400 mb-1">年度发文趋势</p>
                              <div className="flex items-end gap-1 h-12">
                                {keywordMap.yearly_trend.slice(-8).map(([year, count]) => {
                                  const max = Math.max(...keywordMap.yearly_trend.slice(-8).map(([, c]) => c));
                                  return (
                                    <div key={year} className="flex flex-col items-center flex-1" title={`${year}: ${count} 篇`}>
                                      <div
                                        className="w-full bg-primary-400 rounded-t"
                                        style={{ height: `${Math.max(8, (count / max) * 100)}%` }}
                                      />
                                      <span className="text-[9px] text-gray-400 mt-0.5">{year.slice(2)}</span>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* 共现词 */}
                          {keywordMap.cooccurring_keywords.length > 0 && (
                            <div>
                              <p className="text-gray-400 mb-1">共现关键词</p>
                              <div className="flex flex-wrap gap-1">
                                {keywordMap.cooccurring_keywords.slice(0, 10).map(([word, count]) => (
                                  <button
                                    key={word}
                                    onClick={() => router.push(`/search?search=${encodeURIComponent(word)}&search_field=keyword`)}
                                    className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700/60 rounded hover:bg-primary-100 dark:hover:bg-primary-900/40 hover:text-primary-700 transition-colors"
                                  >
                                    {word} <span className="text-gray-400">{count}</span>
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 期刊分布 */}
                          {keywordMap.journal_distribution.length > 0 && (
                            <div>
                              <p className="text-gray-400 mb-1">期刊分布</p>
                              <div className="space-y-1">
                                {keywordMap.journal_distribution.slice(0, 5).map(([journal, count]) => (
                                  <div key={journal} className="flex items-center gap-1.5">
                                    <span className="w-24 truncate text-gray-600 dark:text-gray-300" title={journal}>{journal}</span>
                                    <div className="flex-1 h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                                      <div
                                        className="h-full bg-blue-400 rounded-full"
                                        style={{ width: `${(count / keywordMap.journal_distribution[0][1]) * 100}%` }}
                                      />
                                    </div>
                                    <span className="text-gray-400 w-6 text-right">{count}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 代表论文 */}
                          {keywordMap.representative_papers.length > 0 && (
                            <div>
                              <p className="text-gray-400 mb-1">代表论文</p>
                              <ul className="space-y-1">
                                {keywordMap.representative_papers.slice(0, 5).map((p) => (
                                  <li key={p.id}>
                                    <a href={`/paper/${p.id}`} target="_blank" rel="noopener noreferrer" className="block text-gray-600 dark:text-gray-300 hover:text-primary-600 line-clamp-1">
                                      · {p.title}
                                    </a>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-gray-400 py-2">暂无该关键词的版图数据</p>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-6 sm:py-8 text-gray-400 text-sm">
                  <svg className="w-10 h-10 sm:w-12 sm:h-12 mx-auto mb-2 text-gray-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
                  </svg>
                  {t('net.clickHint')}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </Layout>
  );
}