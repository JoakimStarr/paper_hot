'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import Layout from '@/components/Layout';
import { papersApi } from '@/lib/api';
import { NetworkData, NetworkNode } from '@/types/paper';
import { Loader2, Users, Hash, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';
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

export default function NetworkPage() {
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState<TabType>('authors');
  const [data, setData] = useState<NetworkData | null>(null);
  const [loading, setLoading] = useState(true);
  const [infoNode, setInfoNode] = useState<NetworkNode | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const fetchData = useCallback(async (tab: TabType) => {
    setLoading(true);
    setInfoNode(null);
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

    const nodes: SimNode[] = data.nodes.map(n => ({
      ...n,
      count: n.papers || n.count || 0,
    }));

    const nodeIds = new Set(nodes.map(n => n.id));
    const links: SimLink[] = data.links
      .filter(l => nodeIds.has(l.source) && nodeIds.has(l.target))
      .map(l => ({ ...l, value: l.value || 1 }));

    const colorScale = d3.scaleOrdinal<string>(d3.schemeCategory10);

    const linkWidth = d3.scaleLinear<number>()
      .domain([0, d3.max(links, d => d.value) || 1])
      .range([0.5, 3]);

    const nodeRadius = d3.scaleLinear<number>()
      .domain([0, d3.max(nodes, d => d.count) || 1])
      .range([5, 22]);

    g.append('g')
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
        setInfoNode({
          id: d.id,
          name: d.name,
          group: d.group,
          papers: d.group === 'author' ? d.count : undefined,
          count: d.group === 'keyword' ? d.count : undefined,
        });
      });

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
    };
  }, [data]);

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
                <div className="space-y-2 text-sm">
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
                  {infoNode.papers && (
                    <div>
                      <span className="text-gray-400 block text-xs">论文数</span>
                      <span className="text-gray-900 font-semibold text-lg">{infoNode.papers}</span>
                    </div>
                  )}
                  {infoNode.count && (
                    <div>
                      <span className="text-gray-400 block text-xs">出现次数</span>
                      <span className="text-gray-900 font-semibold text-lg">{infoNode.count}</span>
                    </div>
                  )}
                  <div className="pt-2 border-t border-gray-100 mt-2">
                    <span className="text-gray-400 block text-xs">提示</span>
                    <span className="text-gray-500 text-xs">
                      节点越大表示{infoNode.group === 'author' ? '论文数' : '出现次数'}越多
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