'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import Layout from '@/components/Layout';
import { papersApi } from '@/lib/api';
import { NetworkData, NetworkNode } from '@/types/paper';
import { Loader2, Users, Hash, ChevronRight, ExternalLink } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';

const NetworkGraph = dynamic(() => import('./NetworkGraph'), { ssr: false });

type TabType = 'authors' | 'keywords';

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
  const [activeTab, setActiveTab] = useState<TabType>('authors');
  const [data, setData] = useState<NetworkData | null>(null);
  const [loading, setLoading] = useState(true);
  const [infoNode, setInfoNode] = useState<NetworkNode | null>(null);
  const [highlightedNodeId, setHighlightedNodeId] = useState<string | null>(null);

  const fetchData = useCallback(async (tab: TabType) => {
    setLoading(true);
    setInfoNode(null);
    setHighlightedNodeId(null);
    try {
      if (tab === 'authors') {
        const res = await papersApi.getAuthorNetwork(50);
        setData(res);
      } else {
        const res = await papersApi.getKeywordNetwork(200);
        setData(res);
      }
    } catch (error) {
      console.error('Error fetching network data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(activeTab);
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
      return;
    }
    setInfoNode(node);
    setHighlightedNodeId(node.id);
  }, []);

  const handleConnectedNodeClick = (node: ConnectedNode) => {
    setInfoNode({
      id: node.id,
      name: node.name,
      group: node.group,
      papers: node.group === 'author' ? node.count : undefined,
      count: node.group === 'keyword' ? node.count : undefined,
    });
    setHighlightedNodeId(node.id);
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
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          研究关系网络
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          可视化展示作者合作网络和关键词共现关系
        </p>
      </div>

      <div className="flex gap-4 mb-6">
        <button
          onClick={() => setActiveTab('authors')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'authors'
              ? 'bg-primary-600 text-white'
              : 'bg-white dark:bg-gray-800 border border-gray-300 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:bg-gray-700/50'
          }`}
        >
          <Users className="w-4 h-4" />
          作者合作网络
        </button>
        <button
          onClick={() => setActiveTab('keywords')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'keywords'
              ? 'bg-primary-600 text-white'
              : 'bg-white dark:bg-gray-800 border border-gray-300 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:bg-gray-700/50'
          }`}
        >
          <Hash className="w-4 h-4" />
          关键词共现网络
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      ) : (
        <>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4 mb-4">
            <div className="flex items-center gap-2">
              {highlightedNodeId && (
                <button
                  onClick={handleClearHighlight}
                  className="ml-2 px-3 py-1.5 text-xs bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 rounded-md transition-colors text-gray-600 dark:text-gray-400"
                >
                  清除高亮
                </button>
              )}
              <span className="ml-4 text-sm text-gray-500 dark:text-gray-400">
                {data?.nodes.length || 0} 个节点, {data?.links.length || 0} 条关系 — 鼠标滚轮缩放，拖拽移动
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <NetworkGraph
              data={data}
              highlightedNodeId={highlightedNodeId}
              onNodeClick={handleNodeClick}
            />

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">节点详情</h3>
              {infoNode ? (
                <div className="space-y-3 text-sm">
                  <div>
                    <span className="text-gray-400 block text-xs">名称</span>
                    <span className="text-gray-900 dark:text-white font-medium">{infoNode.name}</span>
                  </div>
                  <div>
                    <span className="text-gray-400 block text-xs">类型</span>
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700">
                      {infoNode.group === 'author' ? <Users className="w-3 h-3" /> : <Hash className="w-3 h-3" />}
                      {infoNode.group === 'author' ? '作者' : '关键词'}
                    </span>
                  </div>
                  {infoNode.papers !== undefined && (
                    <div>
                      <span className="text-gray-400 block text-xs">论文数</span>
                      <span className="text-gray-900 dark:text-white font-semibold text-lg">{infoNode.papers}</span>
                    </div>
                  )}
                  {infoNode.count !== undefined && infoNode.group === 'keyword' && (
                    <div>
                      <span className="text-gray-400 block text-xs">出现次数</span>
                      <span className="text-gray-900 dark:text-white font-semibold text-lg">{infoNode.count}</span>
                    </div>
                  )}

                  {connectedNodes.length > 0 && (
                    <div className="pt-3 border-t border-gray-100 dark:border-gray-700">
                      <span className="text-gray-400 block text-xs mb-2">
                        关联{infoNode.group === 'author' ? '作者' : '关键词'} ({connectedNodes.length})
                      </span>
                      <div className="space-y-1 max-h-64 overflow-y-auto">
                        {connectedNodes.map(node => (
                          <div
                            key={node.id}
                            className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-left text-xs ${
                              highlightedNodeId === node.id ? 'bg-primary-50 dark:bg-primary-900/30 ring-1 ring-primary-200' : ''
                            }`}
                          >
                            <button
                              onClick={() => handleConnectedNodeClick(node)}
                              className="flex items-center gap-2 flex-1 min-w-0 hover:text-primary-600 transition-colors"
                            >
                              <ChevronRight className="w-3 h-3 text-gray-300 flex-shrink-0" />
                              <span className="text-gray-700 dark:text-gray-300 truncate">{node.name}</span>
                            </button>
                            <button
                              onClick={() => handleNavigateToNode(node)}
                              className="flex-shrink-0 p-0.5 hover:bg-gray-100 dark:bg-gray-700 rounded transition-colors"
                              title="查看相关论文"
                            >
                              <ExternalLink className="w-3 h-3 text-gray-400 hover:text-primary-600" />
                            </button>
                            <span className="text-gray-400 flex-shrink-0">
                              {node.linkValue > 1 ? `${node.linkValue}次` : ''}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="pt-2 border-t border-gray-100 dark:border-gray-700 mt-2">
                    <span className="text-gray-400 block text-xs">提示</span>
                    <span className="text-gray-500 dark:text-gray-400 text-xs">
                      点击关联节点可切换查看。点击 <ExternalLink className="w-2.5 h-2.5 inline-block text-gray-400" /> 可跳转搜索相关论文。点击空白处或"清除高亮"恢复全局视图。
                    </span>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-gray-400 text-sm">
                  <svg className="w-12 h-12 mx-auto mb-2 text-gray-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
                  </svg>
                  {activeTab === 'authors'
                    ? '点击节点查看作者信息'
                    : '点击节点查看关键词信息'}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </Layout>
  );
}