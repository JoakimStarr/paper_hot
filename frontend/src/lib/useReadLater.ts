'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  initReadLater, subscribeReadLater,
  isQueuedReadLater, toggleReadLater as toggleReadLaterStore,
} from '@/lib/cache';

/** 订阅服务端"稍后读"队列状态的轻量 hook（乐观更新 + 失败回滚）。 */
export function useReadLater() {
  const [version, setVersion] = useState(0);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let mounted = true;
    const unsub = subscribeReadLater(() => setVersion((v) => v + 1));
    initReadLater().finally(() => { if (mounted) setReady(true); });
    return () => {
      mounted = false;
      unsub();
    };
  }, []);

  const has = useCallback((paperId: string) => isQueuedReadLater(paperId), [version]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggle = useCallback(async (paperId: string) => toggleReadLaterStore(paperId), []);

  return { ready, has, toggle };
}
