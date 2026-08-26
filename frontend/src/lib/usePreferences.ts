'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  initPreferences, subscribePreferences,
  getPreferences, isPreferenceHidden,
  addPreference as addPreferenceStore,
  removePreference as removePreferenceStore,
} from '@/lib/cache';

/**
 * 订阅服务端"不感兴趣"屏蔽项（领域/期刊/关键词/作者）的轻量 hook。
 * version 变化即表示屏蔽集合有变动，调用方可作为 deps 触发列表重取
 * （后端会在列表层过滤命中论文，从而实现全局即时生效）。
 */
export function usePreferences() {
  const [version, setVersion] = useState(0);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let mounted = true;
    const unsub = subscribePreferences(() => setVersion((v) => v + 1));
    initPreferences().finally(() => {
      if (mounted) setReady(true);
    });
    return () => {
      mounted = false;
      unsub();
    };
  }, []);

  const has = useCallback(
    (entity_type: string, entity_value: string) => isPreferenceHidden(entity_type, entity_value),
    [version], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const add = useCallback(async (entity_type: string, entity_value: string) => {
    await addPreferenceStore(entity_type, entity_value);
  }, []);

  const remove = useCallback(async (entity_type: string, entity_value: string) => {
    await removePreferenceStore(entity_type, entity_value);
  }, []);

  return {
    ready,
    version,
    items: getPreferences(),
    has,
    add,
    remove,
  };
}