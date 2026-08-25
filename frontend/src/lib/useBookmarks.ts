'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  initBookmarks, isBookmarked, subscribeBookmarks,
  getBookmarksVersion, toggleBookmark as toggleBookmarkStore,
} from '@/lib/cache';

/** 订阅服务端收藏状态的轻量 hook（乐观更新 + 失败回滚）。 */
export function useBookmarks() {
  const [version, setVersion] = useState(0);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let mounted = true;
    const unsub = subscribeBookmarks(() => setVersion((v) => v + 1));
    initBookmarks().finally(() => { if (mounted) setReady(true); });
    return () => {
      mounted = false;
      unsub();
    };
  }, []);

  const has = useCallback((paperId: string) => isBookmarked(paperId), [version]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggle = useCallback(async (paperId: string) => {
    await toggleBookmarkStore(paperId);
  }, []);

  return { ready, has, toggle };
}
