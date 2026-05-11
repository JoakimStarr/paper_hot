const CACHE_PREFIX = 'pp_';
const CACHE_TTL = 5 * 60 * 1000;
const MAX_ENTRIES = 50;

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

export function getCache<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + key);
    if (!raw) return null;
    const entry: CacheEntry<T> = JSON.parse(raw);
    if (Date.now() - entry.timestamp > CACHE_TTL) {
      localStorage.removeItem(CACHE_PREFIX + key);
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

    const fullKey = CACHE_PREFIX + key;
    const allKeys: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(CACHE_PREFIX)) {
        allKeys.push(k);
      }
    }

    if (allKeys.length >= MAX_ENTRIES) {
      let oldestKey: string | null = null;
      let oldestTime = Infinity;
      for (const k of allKeys) {
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
      }
    }

    localStorage.setItem(fullKey, serialized);
  } catch {
    // localStorage full or unavailable
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

export function getBookmarks(): string[] {
  try {
    const raw = localStorage.getItem(BOOKMARKS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

export function toggleBookmark(paperId: string): boolean {
  const bookmarks = getBookmarks();
  const idx = bookmarks.indexOf(paperId);
  if (idx >= 0) {
    bookmarks.splice(idx, 1);
    localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(bookmarks));
    return false;
  }
  bookmarks.push(paperId);
  localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(bookmarks));
  return true;
}

export function isBookmarked(paperId: string): boolean {
  return getBookmarks().includes(paperId);
}