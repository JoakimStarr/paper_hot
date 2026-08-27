'use client';

/**
 * 主题聚类地图（Canvas 轻量渲染版）。
 *
 * 历史性能问题：旧实现用 Recharts(SVG) 渲染全量散点（数千个带事件监听的 SVG
 * 节点 + Tooltip 悬停 O(N) 扫描），明显卡顿。
 *
 * 轻量化手段（继续在 Canvas 方案上做减法）：
 * - 基础层先渲染到离屏 canvas：悬停/高亮时直接 blit 基础层 + 只画高亮点，
 *   每次 mousemove 的绘制成本从「数千个 arc」降为「一次 drawImage + 一个圆」
 * - 按「簇」批量绘制：每簇一次 beginPath + 多个 arc + 一次 fill，
 *   数千个点只产生 ~k 次填充调用（k = 簇数），而非逐点 fill
 * - 悬停命中用「均匀网格空间索引」：只检查鼠标周围 3×3 个网格单元，
 *   不再每次 mousemove O(N) 全扫
 * - 数据量在服务端已按簇等比例抽样到上限（见 clusters.py MAX_POINTS），
 *   簇大小/代表论文仍用全量统计，视觉密度不变
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2, Map as MapIcon } from 'lucide-react';
import { papersApi } from '@/lib/api';
import { TopicClustersResponse, TopicCluster } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

const PALETTE = [
  '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6',
  '#f97316', '#6366f1', '#84cc16', '#06b6d4', '#d946ef', '#eab308', '#22c55e',
  '#f43f5e', '#0ea5e9', '#a855f7', '#64748b',
];

const POINT_R = 3;        // 点半径（CSS px）
const HIT_R = 9;          // 命中测试半径
const CELL = HIT_R * 2;   // 空间索引网格单元尺寸（CSS px）
const CHART_H = 520;

interface CanvasPoint {
  id: string;
  title: string;
  x: number;   // 数据域 0~100
  y: number;
  px: number;  // CSS px（layout 时由数据域换算）
  py: number;
  color: string;
  clusterId: number;
}

interface Props { onData?: () => void }

export default function ClusterMap({ onData }: Props) {
  const { t } = useLanguage();
  const router = useRouter();
  const [data, setData] = useState<TopicClustersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<TopicCluster | null>(null);

  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const baseRef = useRef<HTMLCanvasElement | null>(null);   // 离屏基础层
  const ptsRef = useRef<CanvasPoint[]>([]);
  const gridRef = useRef<{ cols: number; cells: Map<number, number[]> }>({ cols: 0, cells: new Map() });
  const sizeRef = useRef({ w: 0, h: CHART_H });
  const hoverRef = useRef(-1);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await papersApi.getTopicClusters();
        if (!alive) return;
        setData(res);
        onData?.();
      } catch (e: unknown) {
        if (alive) setError(e instanceof Error ? e.message : 'load failed');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 数据 → 点集（仅存数据域坐标，像素坐标在 layout 里按容器宽度换算）
  useEffect(() => {
    if (!data) return;
    const pts: CanvasPoint[] = [];
    data.clusters.forEach((c, i) => {
      const color = PALETTE[i % PALETTE.length];
      for (const pt of c.points) {
        pts.push({ id: pt.id, title: pt.title, x: pt.x, y: pt.y, px: 0, py: 0, color, clusterId: c.id });
      }
    });
    ptsRef.current = pts;
  }, [data]);

  /** 按当前容器尺寸换算像素坐标并重建空间索引（数据/尺寸变化时调用）。 */
  const layout = useCallback(() => {
    const { w, h } = sizeRef.current;
    const pts = ptsRef.current;
    const cols = Math.max(1, Math.ceil(w / CELL));
    const rows = Math.max(1, Math.ceil(h / CELL));
    const cells = new Map<number, number[]>();
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      p.px = (p.x / 100) * w;
      p.py = (p.y / 100) * h;
      const ci = Math.min(cols - 1, Math.floor(p.px / CELL));
      const cj = Math.min(rows - 1, Math.floor(p.py / CELL));
      const key = cj * cols + ci;
      let arr = cells.get(key);
      if (!arr) { arr = []; cells.set(key, arr); }
      arr.push(i);
    }
    gridRef.current = { cols, cells };
  }, []);

  /** 渲染离屏基础层：网格 + 全部点（按簇批量绘制，选中时淡化其余簇）。 */
  const renderBase = useCallback((selectedId: number | null) => {
    const { w, h } = sizeRef.current;
    if (!w || !h) return;
    const dpr = window.devicePixelRatio || 1;
    let base = baseRef.current;
    if (!base) { base = document.createElement('canvas'); baseRef.current = base; }
    if (base.width !== Math.round(w * dpr)) {
      base.width = Math.round(w * dpr);
      base.height = Math.round(h * dpr);
    }
    const bctx = base.getContext('2d');
    if (!bctx) return;
    bctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    bctx.clearRect(0, 0, w, h);

    // 十字参考网格（浅色，装饰性）
    bctx.strokeStyle = 'rgba(128,128,128,0.12)';
    bctx.lineWidth = 1;
    for (let g = 20; g < 100; g += 20) {
      const gx = (g / 100) * w;
      const gy = (g / 100) * h;
      bctx.beginPath(); bctx.moveTo(gx, 0); bctx.lineTo(gx, h); bctx.stroke();
      bctx.beginPath(); bctx.moveTo(0, gy); bctx.lineTo(w, gy); bctx.stroke();
    }

    // 按簇分组，每簇一次 path + 一次 fill
    const pts = ptsRef.current;
    const groups = new Map<number, { color: string; idxs: number[] }>();
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      let g = groups.get(p.clusterId);
      if (!g) { g = { color: p.color, idxs: [] }; groups.set(p.clusterId, g); }
      g.idxs.push(i);
    }
    groups.forEach((g, cid) => {
      bctx.globalAlpha = selectedId === null ? 0.75 : (cid === selectedId ? 0.95 : 0.10);
      bctx.fillStyle = g.color;
      bctx.beginPath();
      for (let i = 0; i < g.idxs.length; i++) {
        const p = pts[g.idxs[i]];
        bctx.moveTo(p.px + POINT_R, p.py);  // 隔离子路径，避免相邻圆之间出现连线
        bctx.arc(p.px, p.py, POINT_R, 0, Math.PI * 2);
      }
      bctx.fill();
    });
    bctx.globalAlpha = 1;
  }, []);

  /** 主画布：blit 基础层 + 可选的高亮点。悬停路径是 O(1)。 */
  const draw = useCallback((hoverIdx: number) => {
    const canvas = canvasRef.current;
    const base = baseRef.current;
    const { w, h } = sizeRef.current;
    if (!canvas || !base || !w) return;
    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(w * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(base, 0, 0, w, h);

    if (hoverIdx >= 0) {
      const p = ptsRef.current[hoverIdx];
      ctx.globalAlpha = 1;
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.px, p.py, POINT_R + 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.9)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  }, []);

  // 数据 / 选中变化：重建布局与基础层并重绘
  useEffect(() => {
    if (!data) return;
    layout();
    renderBase(selected?.id ?? null);
    draw(hoverRef.current);
  }, [data, selected, layout, renderBase, draw]);

  // 容器尺寸变化重绘（ResizeObserver，仅监听宽度变化）
  useEffect(() => {
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(entries => {
      const width = entries[0]?.contentRect.width ?? 0;
      if (width > 0 && Math.abs(width - sizeRef.current.w) > 1) {
        sizeRef.current.w = width;
        layout();
        renderBase(selected?.id ?? null);
        draw(hoverRef.current);
      }
    });
    ro.observe(el);
    sizeRef.current.w = el.clientWidth || 600;
    layout();
    renderBase(selected?.id ?? null);
    draw(hoverRef.current);
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  /** 最近邻命中：均匀网格索引，只扫鼠标周围 3×3 个单元。 */
  const hitTest = useCallback((mx: number, my: number): number => {
    const { cols, cells } = gridRef.current;
    if (cols === 0) return -1;
    const cx = Math.floor(mx / CELL);
    const cy = Math.floor(my / CELL);
    const pts = ptsRef.current;
    let best = -1, bestD2 = HIT_R * HIT_R;
    for (let gy = Math.max(0, cy - 1); gy <= cy + 1; gy++) {
      for (let gx = Math.max(0, cx - 1); gx <= cx + 1; gx++) {
        const arr = cells.get(gy * cols + gx);
        if (!arr) continue;
        for (const i of arr) {
          const p = pts[i];
          const dx = p.px - mx;
          const dy = p.py - my;
          const d2 = dx * dx + dy * dy;
          if (d2 <= bestD2) { bestD2 = d2; best = i; }
        }
      }
    }
    return best;
  }, []);

  const toLocal = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return { mx: e.clientX - rect.left, my: e.clientY - rect.top };
  };

  const handleMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const { mx, my } = toLocal(e);
    const idx = hitTest(mx, my);
    if (idx === hoverRef.current) return;
    hoverRef.current = idx;
    draw(idx);
    const tip = tipRef.current;
    if (!tip) return;
    if (idx >= 0) {
      const p = ptsRef.current[idx];
      const c = data?.clusters.find(c => c.id === p.clusterId);
      tip.innerHTML = '';
      const title = document.createElement('div');
      title.className = 'text-xs font-medium text-gray-900 dark:text-white line-clamp-3 max-w-xs';
      title.textContent = p.title;
      tip.appendChild(title);
      if (c) {
        const sub = document.createElement('div');
        sub.className = 'text-[10px] text-primary-600 mt-1';
        sub.textContent = c.label;
        tip.appendChild(sub);
      }
      tip.style.display = 'block';
      const flip = mx > (sizeRef.current.w - 180);
      tip.style.left = `${flip ? mx - 170 : mx + 12}px`;
      tip.style.top = `${Math.max(4, my - 40)}px`;
    } else {
      tip.style.display = 'none';
    }
  }, [data, draw, hitTest]);

  const handleLeave = useCallback(() => {
    hoverRef.current = -1;
    draw(-1);
    if (tipRef.current) tipRef.current.style.display = 'none';
  }, [draw]);

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const { mx, my } = toLocal(e);
    const idx = hitTest(mx, my);
    if (idx >= 0) router.push(`/paper/${ptsRef.current[idx].id}`);
  }, [hitTest, router]);

  if (loading) {
    return (
      <div className="flex flex-col justify-center items-center py-12 text-gray-500">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600 mb-3" />
        <div className="text-sm">{t('net.clusterComputing')}</div>
      </div>
    );
  }
  if (error || !data || data.clusters.length === 0) {
    return <div className="text-center py-10 text-sm text-red-500">{error || t('net.noData')}</div>;
  }

  return (
    <div className="grid lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
        <div className="flex items-center gap-2 mb-2 text-xs text-gray-500 dark:text-gray-400">
          <MapIcon className="w-4 h-4" />
          {t('net.clusterScatterHint').replace('{total}', String(data.total))}
        </div>
        <div ref={wrapRef} className="relative w-full" style={{ height: CHART_H }}>
          <canvas
            ref={canvasRef}
            className="w-full h-full cursor-pointer"
            onMouseMove={handleMove}
            onMouseLeave={handleLeave}
            onClick={handleClick}
          />
          <div
            ref={tipRef}
            className="absolute pointer-events-none bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg px-3 py-2 hidden"
          />
        </div>
      </div>

      <div className="space-y-2">
        <div className="text-xs text-gray-500 dark:text-gray-400 px-1">
          {t('net.clusterLegend')}（{data.k}）
        </div>
        <div className="space-y-1.5 max-h-[560px] overflow-y-auto pr-1">
          {data.clusters.map((c, i) => (
            <button
              key={c.id}
              onClick={() => setSelected(selected?.id === c.id ? null : c)}
              className={`w-full text-left px-3 py-2 rounded-lg border transition-colors ${
                selected?.id === c.id
                  ? 'border-primary-400 bg-primary-50 dark:bg-primary-900/30'
                  : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/60'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: PALETTE[i % PALETTE.length] }} />
                <span className="text-xs font-medium text-gray-900 dark:text-white truncate flex-1">{c.label}</span>
                <span className="text-[10px] text-gray-400 shrink-0">{c.size}{t('net.papersUnit')}</span>
              </div>
              <div className="text-[10px] text-gray-400 mt-0.5 pl-4.5 flex items-center gap-2">
                <span>{c.year_range}</span>
              </div>
            </button>
          ))}
        </div>
        {selected && (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div className="text-xs font-semibold text-gray-900 dark:text-white mb-2">{t('net.representativePapers')}</div>
            <div className="space-y-1.5">
              {selected.representative_papers.map(p => (
                <button
                  key={p.id}
                  onClick={() => router.push(`/paper/${p.id}`)}
                  className="block w-full text-left text-xs text-gray-600 dark:text-gray-300 hover:text-primary-600 line-clamp-2"
                >
                  • {p.title}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
