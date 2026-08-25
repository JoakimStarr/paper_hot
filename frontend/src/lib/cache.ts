const CACHE_PREFIX = 'pp_';
const CACHE_TTL = 5 * 60 * 1000;
const MAX_ENTRIES = 50;

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

const cacheKeyIndex: string[] = [];

function initCacheIndex() {
  if (cacheKeyIndex.length > 0) return;
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (k && k.startsWith(CACHE_PREFIX)) {
      cacheKeyIndex.push(k);
    }
  }
}

export function getCache<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + key);
    if (!raw) return null;
    const entry: CacheEntry<T> = JSON.parse(raw);
    if (Date.now() - entry.timestamp > CACHE_TTL) {
      localStorage.removeItem(CACHE_PREFIX + key);
      const idx = cacheKeyIndex.indexOf(CACHE_PREFIX + key);
      if (idx >= 0) cacheKeyIndex.splice(idx, 1);
      return null;
    }
    return entry.data;
  } catch {
    return null;
  }
}

export function setCache<T>(key: string, data: T): void {
  try {
    const entry: CacheEntry<T> = { data, timestamp: Date.now() };
    const serialized = JSON.stringify(entry);
    if (serialized.length > 100000) return;

    initCacheIndex();
    const fullKey = CACHE_PREFIX + key;

    if (cacheKeyIndex.length >= MAX_ENTRIES && cacheKeyIndex.indexOf(fullKey) < 0) {
      let oldestKey: string | null = null;
      let oldestTime = Infinity;
      for (const k of cacheKeyIndex) {
        try {
          const raw = localStorage.getItem(k);
          if (raw) {
            const e: CacheEntry<unknown> = JSON.parse(raw);
            if (e.timestamp < oldestTime) {
              oldestTime = e.timestamp;
              oldestKey = k;
            }
          }
        } catch {}
      }
      if (oldestKey) {
        localStorage.removeItem(oldestKey);
        const idx = cacheKeyIndex.indexOf(oldestKey);
        if (idx >= 0) cacheKeyIndex.splice(idx, 1);
      }
    }

    localStorage.setItem(fullKey, serialized);
    if (cacheKeyIndex.indexOf(fullKey) < 0) {
      cacheKeyIndex.push(fullKey);
    }
  } catch {
  }
}

export function buildCacheKey(params: Record<string, unknown>): string {
  const pairs: string[] = [];
  const sortedKeys = Object.keys(params).sort();
  for (const k of sortedKeys) {
    const v = params[k];
    if (v !== undefined && v !== null && v !== '') {
      pairs.push(`${k}=${v}`);
    }
  }
  return pairs.join('&');
}

const BOOKMARKS_KEY = 'pp_bookmarks';

// —— 收藏：后端持久化（P1-10），localStorage 仅做旧数据一次性迁移 ——
// 内存 Set 作为同步快照，服务端为事实源；未登录体系，身份由 x-user-id 承载。
const bookmarkListeners = new Set<() => void>();
let bookmarksCache: Set<string> = new Set();
let bookmarksHydrated = false;
let bookmarksVersion = 0;

function notifyBookmarks() {
  bookmarksVersion++;
  bookmarkListeners.forEach((cb) => cb());
}

export function subscribeBookmarks(cb: () => void): () => void {
  bookmarkListeners.add(cb);
  return () => bookmarkListeners.delete(cb);
}

export function getBookmarksVersion(): number {
  return bookmarksVersion;
}

/** 应用启动时调用一次：拉取服务端收藏并合并迁移旧的 localStorage 数据。 */
export async function initBookmarks(): Promise<void> {
  if (bookmarksHydrated) return;
  bookmarksHydrated = true;
  const { personalApi } = await import('./api');
  try {
    const res = await personalApi.getFavorites();
    bookmarksCache = new Set(res.papers.map((p) => p.id));
  } catch {
    // 后端不可用时退回本地缓存，保持功能可用
    try {
      const raw = localStorage.getItem(BOOKMARKS_KEY);
      bookmarksCache = new Set(raw ? (JSON.parse(raw) as string[]) : []);
    } catch {
      bookmarksCache = new Set();
    }
  }
  // 迁移：把旧 localStorage 收藏推送到服务端，然后清掉
  try {
    const legacyRaw = localStorage.getItem(BOOKMARKS_KEY);
    if (legacyRaw) {
      const legacy: string[] = JSON.parse(legacyRaw);
      for (const id of legacy) {
        if (!bookmarksCache.has(id)) {
          try {
            const r = await personalApi.toggleFavorite(id);
            if (r.bookmarked) bookmarksCache.add(id);
          } catch { /* 单条失败不阻断 */ }
        }
      }
      localStorage.removeItem(BOOKMARKS_KEY);
    }
  } catch { /* ignore */ }
  notifyBookmarks();
}

export function getBookmarks(): string[] {
  return Array.from(bookmarksCache);
}

export function isBookmarked(paperId: string): boolean {
  return bookmarksCache.has(paperId);
}

/** 切换收藏（服务端为事实源），返回切换后的状态。 */
export async function toggleBookmark(paperId: string): Promise<boolean> {
  const { personalApi } = await import('./api');
  // 乐观更新
  const optimistic = !bookmarksCache.has(paperId);
  if (optimistic) bookmarksCache.add(paperId);
  else bookmarksCache.delete(paperId);
  notifyBookmarks();
  try {
    const res = await personalApi.toggleFavorite(paperId);
    if (res.bookmarked) bookmarksCache.add(paperId);
    else bookmarksCache.delete(paperId);
    notifyBookmarks();
    return res.bookmarked;
  } catch (e) {
    // 失败回滚
    if (optimistic) bookmarksCache.delete(paperId);
    else bookmarksCache.add(paperId);
    notifyBookmarks();
    throw e;
  }
}