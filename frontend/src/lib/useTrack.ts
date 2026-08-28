// 用户行为埋点 hook：批量上报 + 自动刷新。
'use client';

import { useCallback, useRef } from 'react';
import { trackingApi, TrackEvent } from '@/lib/api';

const FLUSH_INTERVAL_MS = 3000;
const MAX_BATCH_SIZE = 20;

/**
 * 轻量埋点 hook：
 * - track() 入队事件，定时批量上报
 * - 组件卸载时 flush 剩余事件
 */
export function useTrack() {
  const queueRef = useRef<TrackEvent[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const flush = useCallback(async () => {
    if (queueRef.current.length === 0) return;
    const batch = queueRef.current.splice(0, MAX_BATCH_SIZE);
    try {
      await trackingApi.trackEvents(batch);
    } catch {
      // 静默失败，不阻塞用户
    }
  }, []);

  const startTimer = useCallback(() => {
    if (timerRef.current) return;
    timerRef.current = setInterval(flush, FLUSH_INTERVAL_MS);
  }, [flush]);

  const track = useCallback(
    (event: TrackEvent) => {
      queueRef.current.push(event);
      startTimer();
      // 超过批次大小立即刷
      if (queueRef.current.length >= MAX_BATCH_SIZE) {
        flush();
      }
    },
    [startTimer, flush],
  );

  return { track, flush };
}
