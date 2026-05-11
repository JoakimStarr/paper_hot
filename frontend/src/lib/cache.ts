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
let bookmarksCache: string[] | null = null;

function loadBookmarks(): string[] {
  if (bookmarksCache !== null) return bookmarksCache;
  try {
    const raw = localStorage.getItem(BOOKMARKS_KEY);
    bookmarksCache = raw ? JSON.parse(raw) : [];
  } catch {
    bookmarksCache = [];
  }
  return bookmarksCache!;
}

function saveBookmarks(bookmarks: string[]) {
  bookmarksCache = bookmarks;
  localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(bookmarks));
}

export function getBookmarks(): string[] {
  return loadBookmarks();
}

export function toggleBookmark(paperId: string): boolean {
  const bookmarks = loadBookmarks();
  const idx = bookmarks.indexOf(paperId);
  if (idx >= 0) {
    bookmarks.splice(idx, 1);
    saveBookmarks([...bookmarks]);
    return false;
  }
  saveBookmarks([...bookmarks, paperId]);
  return true;
}

export function isBookmarked(paperId: string): boolean {
  return loadBookmarks().includes(paperId);
}