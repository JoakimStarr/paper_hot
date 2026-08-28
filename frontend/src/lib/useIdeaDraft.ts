'use client';

import { useCallback, useEffect, useState } from 'react';
import type { TopicIdeaPreferences, TopicIdeaCandidate } from '@/types/paper';

export interface IdeaDraft {
  idea: string;
  preferences: TopicIdeaPreferences;
  /** 各轮候选历史（rounds[i] = 第 i+1 轮候选），用于回溯 */
  rounds: TopicIdeaCandidate[][];
}

const KEY = 'paperpulse-idea-draft';

function load(): IdeaDraft | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const d = JSON.parse(raw);
    return {
      idea: typeof d.idea === 'string' ? d.idea : '',
      preferences: d.preferences || {},
      rounds: Array.isArray(d.rounds) ? d.rounds : [],
    };
  } catch {
    return null;
  }
}

/**
 * 选题灵感向导草稿：localStorage 持久化，刷新/关闭不丢；选定或主动清除时删。
 * 未立项前不落库（避免污染项目列表）。
 */
export function useIdeaDraft() {
  const [draft, setDraft] = useState<IdeaDraft | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setDraft(load());
    setHydrated(true);
  }, []);

  const update = useCallback((patch: Partial<IdeaDraft>) => {
    setDraft((prev) => {
      const next: IdeaDraft = {
        idea: '',
        preferences: {},
        rounds: [],
        ...(prev || {}),
        ...patch,
      };
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        /* 存储失败不阻塞 */
      }
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setDraft(null);
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
  }, []);

  return { draft, hydrated, update, clear };
}
