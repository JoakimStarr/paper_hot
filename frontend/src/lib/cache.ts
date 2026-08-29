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

// —— 手动置顶（P2 置顶改造）：服务端为事实源，内存 Set 同步快照 ——
// 语义与收藏一致，但只有"用户主动置顶"（无分数/趋势自动徽章）。
const pinListeners = new Set<() => void>();
let pinsCache: Set<string> = new Set();
let pinsHydrated = false;
let pinsVersion = 0;

function notifyPins() {
  pinsVersion++;
  pinListeners.forEach((cb) => cb());
}

export function subscribePins(cb: () => void): () => void {
  pinListeners.add(cb);
  return () => pinListeners.delete(cb);
}

export function getPinsVersion(): number {
  return pinsVersion;
}

/** 应用启动时调用一次：拉取服务端手动置顶论文 id。 */
export async function initPins(): Promise<void> {
  if (pinsHydrated) return;
  pinsHydrated = true;
  const { personalApi } = await import('./api');
  try {
    const res = await personalApi.getPins();
    pinsCache = new Set(res.paper_ids || []);
  } catch {
    pinsCache = new Set();
  }
  notifyPins();
}

export function getPins(): string[] {
  return Array.from(pinsCache);
}

export function isPinned(paperId: string): boolean {
  return pinsCache.has(paperId);
}

/** 切换手动置顶的返回结果：pinned 为最终状态；limited 表示已达置顶上限被拒绝。 */
export interface PinToggleResult {
  pinned: boolean;
  limited: boolean;
}

/** 切换手动置顶（服务端为事实源），返回切换后的状态与是否触顶。 */
export async function togglePin(paperId: string): Promise<PinToggleResult> {
  const { personalApi } = await import('./api');
  const optimistic = !pinsCache.has(paperId);
  if (optimistic) pinsCache.add(paperId);
  else pinsCache.delete(paperId);
  notifyPins();
  try {
    const res = await personalApi.togglePin(paperId);
    if (res.pinned) pinsCache.add(paperId);
    else pinsCache.delete(paperId);
    notifyPins();
    return { pinned: res.pinned, limited: false };
  } catch (e) {
    // 已达置顶上限：服务端拒绝（detail 恒为 MAX_PINNED_PAPERS），回滚并返回触顶态
    if (e instanceof Error && e.message === 'MAX_PINNED_PAPERS') {
      pinsCache.delete(paperId);
      notifyPins();
      return { pinned: false, limited: true };
    }
    // 其他失败回滚
    if (optimistic) pinsCache.delete(paperId);
    else pinsCache.add(paperId);
    notifyPins();
    throw e;
  }
}

// —— "不感兴趣"屏蔽（P2）：服务端为事实源，内存快照同步 ——
// 命中任一屏蔽项（领域/期刊/关键词/作者）的论文会被后端在列表层干掉，
// 这里只缓存屏蔽项集合，供管理工作台渲染 + 卡片级状态判断 + 列表刷新信号。
export interface HiddenPreferenceItem {
  entity_type: 'subfield' | 'journal' | 'keyword' | 'author';
  entity_value: string;
}

const prefListeners = new Set<() => void>();
let prefCache: HiddenPreferenceItem[] = [];
let prefHydrated = false;
let prefVersion = 0;

function notifyPreferences() {
  prefVersion++;
  prefListeners.forEach((cb) => cb());
}

export function subscribePreferences(cb: () => void): () => void {
  prefListeners.add(cb);
  return () => prefListeners.delete(cb);
}

export function getPreferencesVersion(): number {
  return prefVersion;
}

/** 应用启动时调用一次：拉取服务端"不感兴趣"屏蔽项。 */
export async function initPreferences(): Promise<void> {
  if (prefHydrated) return;
  prefHydrated = true;
  const { personalApi } = await import('./api');
  try {
    const res = await personalApi.getPreferences();
    prefCache = (res.items || []).filter(
      (i): i is HiddenPreferenceItem => !!i && ['subfield', 'journal', 'keyword', 'author'].includes(i.entity_type),
    );
  } catch {
    prefCache = [];
  }
  notifyPreferences();
}

export function getPreferences(): HiddenPreferenceItem[] {
  return prefCache;
}

export function isPreferenceHidden(entity_type: string, entity_value: string): boolean {
  return prefCache.some((p) => p.entity_type === entity_type && p.entity_value === entity_value);
}

/** 新增一条屏蔽项（乐观添加，失败回滚）。 */
export async function addPreference(entity_type: string, entity_value: string): Promise<void> {
  const { personalApi } = await import('./api');
  const existingIndex = prefCache.findIndex(
    (p) => p.entity_type === entity_type && p.entity_value === entity_value,
  );
  if (existingIndex < 0) {
    prefCache = [...prefCache, { entity_type, entity_value } as HiddenPreferenceItem];
    notifyPreferences();
  }
  try {
    await personalApi.addPreference(entity_type, entity_value);
  } catch (e) {
    if (existingIndex < 0) {
      prefCache = prefCache.filter(
        (p) => !(p.entity_type === entity_type && p.entity_value === entity_value),
      );
      notifyPreferences();
    }
    throw e;
  }
}

/** 删除一条屏蔽项（乐观删除，失败回滚）。 */
export async function removePreference(entity_type: string, entity_value: string): Promise<void> {
  const { personalApi } = await import('./api');
  const existed = prefCache.some((p) => p.entity_type === entity_type && p.entity_value === entity_value);
  if (existed) {
    prefCache = prefCache.filter((p) => !(p.entity_type === entity_type && p.entity_value === entity_value));
    notifyPreferences();
  }
  try {
    await personalApi.removePreference(entity_type, entity_value);
  } catch (e) {
    if (existed) {
      prefCache = [...prefCache, { entity_type, entity_value } as HiddenPreferenceItem];
      notifyPreferences();
    }
    throw e;
  }
}

// —— 应用启动期预初始化（PERF）：收藏 / 置顶 / 屏蔽三个全局 store 在模块首次加载时
// 仅触发一次拉取（各自有 *_hydrated 幂等保护）。这样列表/搜索页进入时，卡片挂载即读到
// 已就绪的快照，避免「每张卡片各自初始化 → 初始化完成 notify → 全列表大规模重渲染」的抖动
// （弱机器上表现为进入页面不丝滑）。卡片内的 useBookmarks/usePins/usePreferences 仍会在
// 挂载时调用 initX，但此时已是 no-op，不会重复拉取。
if (typeof window !== 'undefined') {
  initBookmarks().catch(() => {});
  initPins().catch(() => {});
  initPreferences().catch(() => {});
}
// —— 稍后读队列（工作台优化）：服务端为事实源，内存 Set 同步快照 ——
// 与收藏（长期沉淀）区分：队列强调"待办"，读完移出并计入阅读历史。
const readLaterListeners = new Set<() => void>();
let readLaterCache: Set<string> = new Set();
let readLaterHydrated = false;
let readLaterVersion = 0;

function notifyReadLater() {
  readLaterVersion++;
  readLaterListeners.forEach((cb) => cb());
}

export function subscribeReadLater(cb: () => void): () => void {
  readLaterListeners.add(cb);
  return () => readLaterListeners.delete(cb);
}

/** 应用启动时调用一次：拉取服务端稍后读队列 paper_id。 */
export async function initReadLater(): Promise<void> {
  if (readLaterHydrated) return;
  readLaterHydrated = true;
  const { personalApi } = await import('./api');
  try {
    const res = await personalApi.getReadLater();
    readLaterCache = new Set(res.paper_ids || []);
  } catch {
    readLaterCache = new Set();
  }
  notifyReadLater();
}

export function isQueuedReadLater(paperId: string): boolean {
  return readLaterCache.has(paperId);
}

/** 切换稍后读（乐观更新 + 失败回滚），返回切换后的状态。 */
export async function toggleReadLater(paperId: string): Promise<{ queued: boolean }> {
  const { personalApi } = await import('./api');
  const optimistic = !readLaterCache.has(paperId);
  if (optimistic) readLaterCache.add(paperId);
  else readLaterCache.delete(paperId);
  notifyReadLater();
  try {
    const res = await personalApi.toggleReadLater(paperId);
    if (res.queued) readLaterCache.add(paperId);
    else readLaterCache.delete(paperId);
    notifyReadLater();
    return { queued: res.queued };
  } catch (e) {
    if (optimistic) readLaterCache.delete(paperId);
    else readLaterCache.add(paperId);
    notifyReadLater();
    throw e;
  }
}

// —— 推荐反馈写入后的缓存同步 ——
/** 外部路径（如 /personal/recommend-feedback 的"少推这类"）改了服务端屏蔽项时强制重拉。 */
export async function refreshPreferences(): Promise<void> {
  prefHydrated = false;
  await initPreferences();
}
