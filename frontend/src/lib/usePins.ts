'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  initPins, isPinned, subscribePins,
  getPinsVersion, togglePin as togglePinStore,
} from '@/lib/cache';
import type { PinToggleResult } from '@/lib/cache';

/** 订阅服务端手动置顶状态的轻量 hook（乐观更新 + 失败回滚）。 */
export function usePins() {
  const [version, setVersion] = useState(0);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let mounted = true;
    const unsub = subscribePins(() => setVersion((v) => v + 1));
    initPins().finally(() => { if (mounted) setReady(true); });
    return () => {
      mounted = false;
      unsub();
    };
  }, []);

  const has = useCallback((paperId: string) => isPinned(paperId), [version]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggle = useCallback(async (paperId: string): Promise<PinToggleResult> => {
    return togglePinStore(paperId);
  }, []);

  return { ready, has, toggle, version: getPinsVersion() };
}