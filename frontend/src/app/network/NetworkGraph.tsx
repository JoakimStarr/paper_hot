'use client';

import React, { useEffect, useRef, useMemo } from 'react';
import * as d3 from 'd3';
import { NetworkData, NetworkNode } from '@/types/paper';

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

function getLinkNodeId(node: string | SimNode | { id?: string }): string {
  if (typeof node === 'string') return node;
  if (node && 'id' in node && typeof node.id === 'string') return node.id;
  return String(node);
}

interface NetworkGraphProps {
  data: NetworkData | null;
  highlightedNodeId: string | null;
  onNodeClick: (node: NetworkNode) => void;
}

export default function NetworkGraph({ data, highlightedNodeId, onNodeClick }: NetworkGraphProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const nodeGroupsRef = useRef<any>(null);
  const linkLinesRef = useRef<any>(null);
  const simulationRef = useRef<d3.Simulation<SimNode, undefined> | null>(null);
  const initializedRef = useRef(false);
  const gRef = useRef<any>(null);

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

  useEffect(() => {
    if (!data || !svgRef.current || !containerRef.current) return;

    const width = containerRef.current.clientWidth;
    const height = Math.min(600, window.innerHeight - 400);

    const nodes: SimNode[] = data.nodes.map(n => ({
      ...n,
      count: n.papers || n.count || 0,
    }));

    const nodeIds = new Set(nodes.map(n => n.id));
    const links: SimLink[] = data.links
      .filter(l => {
        const sId = getLinkNodeId(l.source);
        const tId = getLinkNodeId(l.target);
        return nodeIds.has(sId) && nodeIds.has(tId);
      })
      .map(l => ({ ...l, value: l.value || 1 }));

    const colorScale = d3.scaleOrdinal<string>(d3.schemeCategory10);
    const linkWidthScale = d3.scaleLinear<number>()
      .domain([0, d3.max(links, d => d.value) || 1])
      .range([0.5, 3]);
    const nodeRadiusScale = d3.scaleLinear<number>()
      .domain([0, d3.max(nodes, d => d.count) || 1])
      .range([5, 22]);

    if (!initializedRef.current) {
      d3.select(svgRef.current).selectAll('*').remove();

      const svg = d3.select(svgRef.current)
        .attr('width', width)
        .attr('height', height);

      const g = svg.append('g');
      gRef.current = g;

      const zoom = d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.2, 5])
        .on('zoom', (event) => {
          g.attr('transform', event.transform);
        });

      svg.call(zoom);
      svg.on('click', () => {
        onNodeClick({ id: '', name: '', group: '' });
      });

      initializedRef.current = true;
    } else {
      if (gRef.current) {
        gRef.current.selectAll('*').remove();
      } else {
        const g = d3.select(svgRef.current).select('g');
        g.selectAll('*').remove();
        gRef.current = g;
      }
    }

    const g = gRef.current as d3.Selection<SVGGElement, unknown, null, undefined>;

    linkLinesRef.current = g.append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', '#ddd')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', d => linkWidthScale(d.value));

    const nodeGroup = g.append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation();
        onNodeClick({
          id: d.id,
          name: d.name,
          group: d.group,
          papers: d.group === 'author' ? d.count : undefined,
          count: d.group === 'keyword' ? d.count : undefined,
        });
      });

    nodeGroupsRef.current = nodeGroup;

    nodeGroup.append('circle')
      .attr('r', d => nodeRadiusScale(d.count))
      .attr('fill', d => colorScale(d.group + d.id))
      .attr('stroke', '#fff')
      .attr('stroke-width', 1.5);

    nodeGroup.append('text')
      .text(d => d.name.length > 8 ? d.name.slice(0, 8) + '...' : d.name)
      .attr('font-size', d => Math.max(8, nodeRadiusScale(d.count) * 0.3))
      .attr('dx', 0)
      .attr('dy', '0.3em')
      .attr('text-anchor', 'middle')
      .attr('fill', '#333')
      .attr('pointer-events', 'none');

    if (simulationRef.current) {
      simulationRef.current.stop();
    }

    const simulation = d3.forceSimulation<SimNode>(nodes)
      .force('link', d3.forceLink<SimNode, SimLink>(links).id(d => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(d => nodeRadiusScale((d as SimNode).count) + 2));

    simulationRef.current = simulation;

    simulation.on('tick', () => {
      g.selectAll<SVGLineElement, SimLink>('line')
        .attr('x1', d => (d.source as SimNode).x!)
        .attr('y1', d => (d.source as SimNode).y!)
        .attr('x2', d => (d.target as SimNode).x!)
        .attr('y2', d => (d.target as SimNode).y!);

      nodeGroup.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    return () => {
      if (simulationRef.current) {
        simulationRef.current.stop();
      }
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

  return (
    <div ref={containerRef} className="lg:col-span-3 bg-white rounded-lg shadow-sm border overflow-hidden">
      <svg ref={svgRef} className="w-full" />
    </div>
  );
}