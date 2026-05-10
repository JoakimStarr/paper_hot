'use client';

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import Layout from '@/components/Layout';
import { papersApi } from '@/lib/api';
import { NetworkData, NetworkNode } from '@/types/paper';
import { Loader2, Users, Hash, ZoomIn, ZoomOut, RotateCcw, ChevronRight } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import * as d3 from 'd3';

type TabType = 'authors' | 'keywords';

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  name: string;
  count: number;
  group: string;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  value: number;
}

interface ConnectedNode {
  id: string;
  name: string;
  group: string;
  linkValue: number;
  count: number;
}

export default function NetworkPage() {
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState<TabType>('authors');
  const [data, setData] = useState<NetworkData | null>(null);
  const [loading, setLoading] = useState(true);
  const [infoNode, setInfoNode] = useState<NetworkNode | null>(null);
  const [highlightedNodeId, setHighlightedNodeId] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const nodeGroupsRef = useRef<any>(null);
  const linkLinesRef = useRef<any>(null);

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
      const sourceId = typeof link.source === 'string' ? link.source : (link.source as any).id || link.source;
      const targetId = typeof link.target === 'string' ? link.target : (link.target as any).id || link.target;

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

  useEffect(() => {
    if (!data || !svgRef.current || !containerRef.current) return;

    const width = containerRef.current.clientWidth;
    const height = Math.min(600, window.innerHeight - 400);

    d3.select(svgRef.current).selectAll('*').remove();

    const svg = d3.select(svgRef.current)
      .attr('width', width)
      .attr('height', height);

    const g = svg.append('g');

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 5])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });

    svg.call(zoom);
    svg.on('click', () => {
      setInfoNode(null);
      setHighlightedNodeId(null);
    });

    const nodes: SimNode[] = data.nodes.map(n => ({
      ...n,
      count: n.papers || n.count || 0,
    }));

    const nodeIds = new Set(nodes.map(n => n.id));
    const links: SimLink[] = data.links
      .filter(l => {
        const sId = typeof l.source === 'string' ? l.source : (l.source as any).id || l.source;
        const tId = typeof l.target === 'string' ? l.target : (l.target as any).id || l.target;
        return nodeIds.has(sId) && nodeIds.has(tId);
      })
      .map(l => ({ ...l, value: l.value || 1 }));

    const colorScale = d3.scaleOrdinal<string>(d3.schemeCategory10);

    const linkWidth = d3.scaleLinear<number>()
      .domain([0, d3.max(links, d => d.value) || 1])
      .range([0.5, 3]);

    const nodeRadius = d3.scaleLinear<number>()
      .domain([0, d3.max(nodes, d => d.count) || 1])
      .range([5, 22]);

    linkLinesRef.current = g.append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', '#ddd')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', d => linkWidth(d.value));

    const nodeGroup = g.append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation();
        const papers = d.group === 'author' ? d.count : undefined;
        const count = d.group === 'keyword' ? d.count : undefined;
        setInfoNode({
          id: d.id,
          name: d.name,
          group: d.group,
          papers,
          count,
        });
        setHighlightedNodeId(d.id);
      });

    nodeGroupsRef.current = nodeGroup;

    nodeGroup.append('circle')
      .attr('r', d => nodeRadius(d.count))
      .attr('fill', d => colorScale(d.group + d.id))
      .attr('stroke', '#fff')
      .attr('stroke-width', 1.5);

    nodeGroup.append('text')
      .text(d => d.name.length > 8 ? d.name.slice(0, 8) + '...' : d.name)
      .attr('font-size', d => Math.max(8, nodeRadius(d.count) * 0.3))
      .attr('dx', 0)
      .attr('dy', '0.3em')
      .attr('text-anchor', 'middle')
      .attr('fill', '#333')
      .attr('pointer-events', 'none');

    const simulation = d3.forceSimulation<SimNode>(nodes)
      .force('link', d3.forceLink<SimNode, SimLink>(links).id(d => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(d => nodeRadius((d as SimNode).count) + 2));

    simulation.on('tick', () => {
      g.selectAll<SVGLineElement, SimLink>('line')
        .attr('x1', d => (d.source as SimNode).x!)
        .attr('y1', d => (d.source as SimNode).y!)
        .attr('x2', d => (d.target as SimNode).x!)
        .attr('y2', d => (d.target as SimNode).y!);

      nodeGroup.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
      nodeGroupsRef.current = null;
      linkLinesRef.current = null;
    };
  }, [data]);

  useEffect(() => {
    if (!nodeGroupsRef.current || !linkLinesRef.current) return;

    const nodeGroups = nodeGroupsRef.current as d3.Selection<d3.BaseType, SimNode, SVGGElement, unknown>;
    const linkLines = linkLinesRef.current as d3.Selection<d3.BaseType, SimLink, SVGGElement, unknown>;
    const connectedIds = new Set(connectedNodes.map(n => n.id));

    nodeGroups
      .selectAll<SVGCircleElement, SimNode>('circle')
      .transition()
      .duration(300)
      .attr('opacity', (d: SimNode) => {
        if (!highlightedNodeId) return 1;
        if (d.id === highlightedNodeId) return 1;
        if (connectedIds.has(d.id)) return 0.85;
        return 0.15;
      });

    nodeGroups
      .selectAll<SVGTextElement, SimNode>('text')
      .transition()
      .duration(300)
      .attr('opacity', (d: SimNode) => {
        if (!highlightedNodeId) return 1;
        if (d.id === highlightedNodeId) return 1;
        if (connectedIds.has(d.id)) return 0.85;
        return 0.1;
      });

    linkLines
      .transition()
      .duration(300)
      .attr('stroke-opacity', (d: SimLink) => {
        if (!highlightedNodeId) return 0.6;
        const sId = (d.source as SimNode).id;
        const tId = (d.target as SimNode).id;
        if (sId === highlightedNodeId || tId === highlightedNodeId) return 0.8;
        return 0.05;
      })
      .attr('stroke', (d: SimLink) => {
        if (!highlightedNodeId) return '#ddd';
        const sId = (d.source as SimNode).id;
        const tId = (d.target as SimNode).id;
        if (sId === highlightedNodeId || tId === highlightedNodeId) return '#4f46e5';
        return '#ddd';
      });
  }, [highlightedNodeId, connectedNodes]);

  const handleZoomIn = () => {
    if (svgRef.current) {
      d3.select(svgRef.current).transition().duration(300).call(
        d3.zoom<SVGSVGElement, unknown>().on('zoom', () => {}).scaleBy, 1.3
      );
    }
  };

  const handleZoomOut = () => {
    if (svgRef.current) {
      d3.select(svgRef.current).transition().duration(300).call(
        d3.zoom<SVGSVGElement, unknown>().on('zoom', () => {}).scaleBy, 0.7
      );
    }
  };

  const handleReset = () => {
    if (svgRef.current) {
      d3.select(svgRef.current).transition().duration(500).call(
        d3.zoom<SVGSVGElement, unknown>().transform as any, d3.zoomIdentity.translate(0, 0).scale(1)
      );
    }
  };

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

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          研究关系网络
        </h1>
        <p className="text-gray-600">
          可视化展示作者合作网络和关键词共现关系
        </p>
      </div>

      <div className="flex gap-4 mb-6">
        <button
          onClick={() => setActiveTab('authors')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'authors'
              ? 'bg-primary-600 text-white'
              : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'
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
              : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'
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
          <div className="bg-white rounded-lg shadow-sm border p-4 mb-4">
            <div className="flex items-center gap-2">
              <button onClick={handleZoomIn} className="p-2 hover:bg-gray-100 rounded-lg transition-colors" title="放大">
                <ZoomIn className="w-4 h-4 text-gray-500" />
              </button>
              <button onClick={handleZoomOut} className="p-2 hover:bg-gray-100 rounded-lg transition-colors" title="缩小">
                <ZoomOut className="w-4 h-4 text-gray-500" />
              </button>
              <button onClick={handleReset} className="p-2 hover:bg-gray-100 rounded-lg transition-colors" title="重置">
                <RotateCcw className="w-4 h-4 text-gray-500" />
              </button>
              {highlightedNodeId && (
                <button
                  onClick={() => { setHighlightedNodeId(null); setInfoNode(null); }}
                  className="ml-2 px-3 py-1.5 text-xs bg-gray-100 hover:bg-gray-200 rounded-md transition-colors text-gray-600"
                >
                  清除高亮
                </button>
              )}
              <span className="ml-4 text-sm text-gray-500">
                {data?.nodes.length || 0} 个节点, {data?.links.length || 0} 条关系 — 可拖拽缩放
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div ref={containerRef} className="lg:col-span-3 bg-white rounded-lg shadow-sm border overflow-hidden">
              <svg ref={svgRef} className="w-full" />
            </div>

            <div className="bg-white rounded-lg shadow-sm border p-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">节点详情</h3>
              {infoNode ? (
                <div className="space-y-3 text-sm">
                  <div>
                    <span className="text-gray-400 block text-xs">名称</span>
                    <span className="text-gray-900 font-medium">{infoNode.name}</span>
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
                      <span className="text-gray-900 font-semibold text-lg">{infoNode.papers}</span>
                    </div>
                  )}
                  {infoNode.count !== undefined && infoNode.group === 'keyword' && (
                    <div>
                      <span className="text-gray-400 block text-xs">出现次数</span>
                      <span className="text-gray-900 font-semibold text-lg">{infoNode.count}</span>
                    </div>
                  )}

                  {connectedNodes.length > 0 && (
                    <div className="pt-3 border-t border-gray-100">
                      <span className="text-gray-400 block text-xs mb-2">
                        关联{infoNode.group === 'author' ? '作者' : '关键词'} ({connectedNodes.length})
                      </span>
                      <div className="space-y-1 max-h-64 overflow-y-auto">
                        {connectedNodes.map(node => (
                          <button
                            key={node.id}
                            onClick={() => handleConnectedNodeClick(node)}
                            className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left text-xs transition-colors hover:bg-gray-50 ${
                              highlightedNodeId === node.id ? 'bg-primary-50 ring-1 ring-primary-200' : ''
                            }`}
                          >
                            <ChevronRight className="w-3 h-3 text-gray-300 flex-shrink-0" />
                            <span className="text-gray-700 truncate flex-1">{node.name}</span>
                            <span className="text-gray-400 flex-shrink-0">
                              {node.linkValue > 1 ? `${node.linkValue}次` : ''}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="pt-2 border-t border-gray-100 mt-2">
                    <span className="text-gray-400 block text-xs">提示</span>
                    <span className="text-gray-500 text-xs">
                      点击关联节点可切换查看。点击空白处或"清除高亮"恢复全局视图。
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