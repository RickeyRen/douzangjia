export type Collection = {
  id: string;
  name: string;
  itemCount: number;
  lastSeenAt: number;
};

export type LibrarySource = {
  id: string;
  kind: "post" | "recommend" | "like" | "favorite_collection" | "favorite_video" | "favorite_music" | "favorite_series" | "favorite_drama" | "watch_history" | "watch_later" | "reservation" | "following";
  remoteId: string;
  name: string;
  declaredCount: number | null;
  discoveredCount: number;
  archivedCount: number;
  missingCount: number;
  syncStatus: "never" | "running" | "complete" | "incomplete" | "failed";
  complete: boolean;
  lastFullScanAt: number | null;
  lastIncrementalScanAt: number | null;
  errorCode: string | null;
  autoDownloadEnabled?: boolean;
  downloadPolicyUpdatedAt?: number | null;
};

export type MediaFile = {
  id: number;
  index: number;
  type: string;
  byteSize: number | null;
  mimeType: string | null;
  url: string;
  posterUrl?: string;
  relativePath?: string | null;
  checksumSha256?: string | null;
  completedAt?: number | null;
  technical?: MediaTechnical;
};

export type MediaTechnical = {
  width: number | null;
  height: number | null;
  codec: string | null;
  fps: number | null;
  bitRate: number | null;
  durationMs: number | null;
  probeStatus: "pending" | "ready" | "unavailable" | "failed";
  probedAt: number | null;
};

export type RemoteAvailability = {
  status: "available" | "deleted" | "private" | "restricted" | "auth_required" | "rate_limited" | "unknown";
  checkedAt: number | null;
  evidenceCode: string | null;
  lastAvailableAt: number | null;
};

export type FeedItem = {
  awemeId: string;
  creatorId: string | null;
  author: string;
  description: string;
  type: "video" | "gallery";
  publishedAt: number | null;
  archivedAt: number;
  sourceUrl: string | null;
  coverUrl?: string | null;
  thumbnailUrl?: string | null;
  starred?: boolean;
  starredAt?: number | null;
  albums?: Array<{ id: number; name: string }>;
  tags?: string[];
  note?: string | null;
  creator?: { id: string; nickname: string; uniqueId: string | null; avatarUrl: string | null } | null;
  douyin?: {
    statistics: Record<string, number>;
    durationMs: number | null;
    hashtags: string[];
    music: Record<string, unknown> | null;
    visibility: string;
  };
  remoteAvailability?: RemoteAvailability;
  collections: Array<{ id: string; name: string }>;
  media: MediaFile[];
  local: LocalArchiveState;
};

export type SourceEntity = {
  id: string;
  type: "music" | "series" | "drama" | "reservation" | "external";
  title: string;
  subtitle: string | null;
  coverUrl: string | null;
  sourceUrl: string | null;
  metadata: Record<string, unknown>;
};

export type CreatorSubscription = {
  creatorId?: string;
  enabled: boolean;
  scanIntervalSeconds: number;
  archiveNewItems: boolean;
  lastScanAt: number | null;
  nextScanAt: number | null;
  lastErrorCode: string | null;
};

export type Creator = {
  id: string;
  nickname: string;
  uniqueId: string | null;
  avatarUrl: string | null;
  followerCount: number | null;
  postCount: number | null;
  knownItemCount: number;
  archivedItemCount: number;
  lastSeenAt: number;
  subscription: CreatorSubscription | null;
};

export type ArchiveBatch = {
  id: number;
  kind: "item" | "source" | "creator" | "selection" | "missing";
  targetId: string;
  status: string;
  discoveredCount?: number;
  completedCount?: number;
  failedCount?: number;
  downloadedBytes?: number;
  totalBytes?: number | null;
  errorCode?: string | null;
};

export type DashboardActivity = {
  state: "syncing_and_downloading" | "syncing" | "downloading" | "idle";
  sync: SyncRun | null;
  sources: Array<{
    id: string;
    kind: LibrarySource["kind"];
    name: string;
    discovered: number;
    remoteTotal: number | null;
  }>;
  downloads: DownloadJob[];
};

export type DashboardSnapshot = {
  storage: { totalBytes: number; usedBytes: number; freeBytes: number; archiveBytes: number; usedPercent: number };
  system: { cpuCount: number; cpuLoadPercent: number; loadAverage1m: number; loadAverage5m: number; loadAverage15m: number; memoryTotalBytes: number; memoryUsedBytes: number; processMemoryBytes: number; browserProcessCount: number; browserMemoryBytes: number };
  library: { items: number; archivedItems: number; mediaFiles: number; creators: number; sources: number; completeSources: number; incompleteSources: number; neverSyncedSources: number; discoveredLinks: number; archivedBytes: number };
  queue: DownloadSummary;
  throughput: {
    today: ThroughputWindow;
    sevenDays: ThroughputWindow;
    thirtyDays: ThroughputWindow;
    lifetime: { bytes: number };
    historyStartedAt: number | null;
  };
  health: { recentErrors: number; uptimeSeconds: number; latestSync: SyncRun | null };
  activity: DashboardActivity;
  account: DouyinHealth;
  runtime: DashboardRuntime;
  sources: SourceProgress[];
  generatedAt: number;
};

export type ThroughputWindow = {
  bytes: number;
  previousBytes: number;
  deltaBytes: number;
  comparisonAvailable: boolean;
};

export type DashboardRuntime = {
  serviceCount: number;
  application: {
    status: string;
    memoryBytes: number;
    cpuLoadPercent: number;
    uptimeSeconds: number;
    lastActivityAt: number | null;
  };
  downloader: {
    status: string;
    workerCount: number;
    activeWorkers: number;
    activeDownloads: number;
    pendingDownloads: number;
    speedBps: number;
    lastActivityAt: number | null;
  };
  browser: {
    status: string;
    started: boolean;
    busy: boolean;
    processCount: number;
    memoryBytes: number;
    lastActivityAt: number | null;
  };
};

export type DouyinHealth = {
  sessionStored: boolean;
  status: "healthy" | "degraded" | "expired" | "checking" | "unknown";
  lastVerifiedAt: number | null;
  lastSyncAt: number | null;
  lastFailureAt: number | null;
  errorCode: string | null;
  consecutiveFailures: number;
  account: { id: string | null; nickname: string | null; uniqueId: string | null; avatarUrl: string | null } | null;
};

export type SourceProgress = {
  id: string;
  kind: LibrarySource["kind"];
  name: string;
  autoDownloadEnabled: boolean;
  downloadPolicyUpdatedAt: number | null;
  discovered: number;
  archived: number;
  pending: number;
  running: number;
  retry: number;
  failed: number;
  archivedBytes: number;
  knownTotalBytes: number;
  remoteTotal: number | null;
  remoteComplete: boolean;
  coveragePercent: number;
  syncStatus: string;
  lastSyncAt: number | null;
  errorCode: string | null;
};

export type MetricPoint = {
  sampledAt: number;
  downloadSpeedBps: number;
  downloadedBytes: number;
  cpuLoadPercent: number;
  memoryUsedBytes: number;
  processMemoryBytes: number;
  diskUsedBytes: number;
  diskFreeBytes: number;
  archiveBytes: number;
};

export type LocalArchiveState = {
  state: "downloaded" | "downloading" | "waiting" | "retry" | "failed";
  readyAssets: number;
  totalAssets: number;
  downloadedBytes: number;
  totalBytes: number | null;
};

export type LoginStatus = {
  id: string;
  state: "starting" | "awaiting_scan" | "authenticated" | "expired" | "failed" | "cancelled";
  expiresAt: string;
  hasScreenshot: boolean;
  errorCode?: string;
};

export type PointerPoint = { x: number; y: number };
export type PointerEventPayload = PointerPoint & { action: "down" | "move" | "up" };

export type BootstrapStatus = {
  configured: boolean;
  ownerSetupRequired: boolean;
  authenticated: boolean;
  douyinAuthenticated: boolean;
  douyinHealth?: DouyinHealth;
};

export type DownloadJob = {
  id: number;
  kind: string;
  remoteId: string;
  author: string;
  description: string;
  collections: string[];
  status: string;
  attempts: number;
  nextAttemptAt: number;
  errorCode: string | null;
  updatedAt: number;
  currentAssetIndex: number | null;
  downloadedBytes: number;
  totalBytes: number | null;
  speedBps: number;
  etaSeconds: number | null;
  assets: DownloadAsset[];
};

export type DownloadAsset = {
  index: number;
  fileName: string;
  mediaType: string;
  status: string;
  downloadedBytes: number;
  totalBytes: number | null;
  speedBps: number;
  etaSeconds: number | null;
  updatedAt: number | null;
};

export type DownloadSummary = {
  pending: number;
  running: number;
  retry: number;
  failed: number;
  completed: number;
  downloadedBytes: number;
  totalBytes: number | null;
  speedBps: number;
  etaSeconds: number | null;
};

export type DownloadSnapshot = {
  summary: DownloadSummary;
  items: DownloadJob[];
};

export type SyncRun = {
  id: number;
  mode: string;
  phase: string;
  status: string;
  discovered: number;
  enqueued: number;
  errorCode: string | null;
  startedAt: number;
  finishedAt: number | null;
};

export type SyncHealthState = "ok" | "syncing" | "stale" | "failing" | "login_required" | "never";

export type SyncHealth = {
  state: SyncHealthState;
  lastSuccessAt: number | null;
  lastAttemptAt: number | null;
  lastErrorCode: string | null;
  consecutiveFailures: number;
  intervalSeconds: number;
  staleAfterSeconds: number;
  browser: string;
};

export type HomeShelf = {
  id: string;
  kind: LibrarySource["kind"];
  name: string;
  itemCount: number;
  lastSeenAt: number | null;
  covers: string[];
};

export type HomeCreator = {
  id: string;
  nickname: string;
  uniqueId: string | null;
  avatarUrl: string | null;
  itemCount: number;
};

export type HomeSnapshot = {
  stats: {
    items: number;
    videos: number;
    galleries: number;
    downloadedItems: number;
    archivedBytes: number;
    creators: number;
    starred: number;
    gone: number;
    remoteChecked: number;
  };
  health: SyncHealth;
  recent: FeedItem[];
  starred: FeedItem[];
  gone: FeedItem[];
  shelves: HomeShelf[];
  creators: HomeCreator[];
};

export type FeedSort = "archived" | "published" | "source" | "starred" | "random" | "album" | "relevance";
export type DurationBucket = "short" | "medium" | "long";
export type PeriodBucket = "week" | "month" | "quarter" | "year";

export type Album = {
  id: number;
  name: string;
  itemCount: number;
  createdAt: number;
  updatedAt: number;
  lastAddedAt: number | null;
  covers: string[];
};

export type TagSummary = { tag: string; itemCount: number };

export type FeedQuery = {
  sourceId?: string;
  creatorId?: string;
  collectionId?: string;
  author?: string;
  type?: "video" | "gallery";
  search?: string;
  sort?: FeedSort;
  seed?: number;
  downloaded?: boolean;
  starred?: boolean;
  albumId?: number;
  tag?: string;
  remote?: string;
  duration?: DurationBucket;
  period?: PeriodBucket;
  cursor?: string;
  limit?: number;
};

const DURATION_BOUNDS: Record<DurationBucket, [number | null, number | null]> = {
  short: [null, 60],
  medium: [60, 300],
  long: [300, null],
};

export function periodStart(period: PeriodBucket, now = new Date()): number {
  const start = new Date(now);
  if (period === "year") start.setMonth(0, 1);
  else start.setDate(start.getDate() - { week: 7, month: 30, quarter: 90 }[period]);
  start.setHours(0, 0, 0, 0);
  return Math.floor(start.getTime() / 1000);
}

export type Page<T> = { items: T[]; nextCursor: string | null };

export type RuntimeSettings = {
  sync_interval_seconds: number;
  download_workers: number;
  remote_check_per_day: number;
  notifications: Record<string, unknown>;
};

export type SettingsPayload = {
  values: RuntimeSettings;
  defaults: RuntimeSettings;
  overridden: string[];
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

function csrfToken(): string | undefined {
  const entry = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("archive_csrf="));
  return entry ? decodeURIComponent(entry.split("=", 2)[1]) : undefined;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method && !["GET", "HEAD"].includes(init.method.toUpperCase())) {
    const csrf = csrfToken();
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      code?: string;
      message?: string;
    };
    throw new ApiError(response.status, payload.code ?? "REQUEST_FAILED", payload.message ?? "请求失败");
  }
  return (await response.json()) as T;
}

export const fetchStatus = () => request<BootstrapStatus>("/api/status");
export const setupAdmin = (username: string, password: string) =>
  request<{ configured: boolean; username: string }>("/api/setup", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
export const loginAdmin = (username: string, password: string) =>
  request<{ authenticated: boolean; username: string }>("/api/session", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
export const migrateOwner = (username: string, currentPassword: string) =>
  request<{ configured: boolean; authenticated: boolean; username: string }>("/api/admin/migrate-owner", {
    method: "POST",
    body: JSON.stringify({ username, currentPassword }),
  });
export const fetchCollections = () => request<{ items: Collection[] }>("/api/collections");
export const fetchLibrarySources = () => request<{ items: LibrarySource[] }>("/api/library/sources");
export const fetchSourceEntities = ({ sourceId, cursor }: { sourceId: string; cursor?: string }) => {
  const query = new URLSearchParams({ sourceId, limit: "20" });
  if (cursor) query.set("cursor", cursor);
  return request<{ items: SourceEntity[]; nextCursor: string | null }>(`/api/library/entities?${query}`);
};
export const fetchJobs = () => request<DownloadSnapshot>("/api/jobs?limit=50");
export const fetchSyncRuns = () => request<{ items: SyncRun[] }>("/api/sync/runs?limit=20");
export const fetchDashboard = () => request<DashboardSnapshot>("/api/dashboard");
export const fetchDashboardSeries = (window: "15m" | "24h" | "7d" = "24h") =>
  request<{ window: string; items: MetricPoint[] }>(`/api/dashboard/series?window=${window}`);
export const updateSourceDownloadPolicy = (sourceId: string, enabled: boolean) =>
  request<SourceProgress>(`/api/library/sources/${encodeURIComponent(sourceId)}/download-policy`, {
    method: "PUT",
    body: JSON.stringify({ enabled }),
  });
export const checkRemoteAvailability = (remoteId: string) =>
  request<RemoteAvailability>(`/api/items/${encodeURIComponent(remoteId)}/remote-check`, { method: "POST" });
export const fetchArchiveBatches = () => request<{ items: ArchiveBatch[] }>("/api/archive/batches?limit=20");
export const controlArchiveBatch = (batchId: number, action: "pause" | "resume" | "cancel") =>
  request<ArchiveBatch>(`/api/archive/batches/${batchId}/${action}`, { method: "POST" });
export function feedQueryString(query: FeedQuery): string {
  const params = new URLSearchParams({ limit: String(query.limit ?? 24) });
  const text: Array<[keyof FeedQuery, string]> = [
    ["sourceId", "sourceId"],
    ["creatorId", "creatorId"],
    ["collectionId", "collectionId"],
    ["author", "author"],
    ["type", "type"],
    ["search", "search"],
    ["sort", "sort"],
    ["cursor", "cursor"],
  ];
  for (const [key, name] of text) {
    const value = query[key];
    if (typeof value === "string" && value) params.set(name, value);
  }
  if (query.albumId) params.set("albumId", String(query.albumId));
  if (query.tag) params.set("tag", query.tag);
  if (query.remote) params.set("remote", query.remote);
  if (query.duration) {
    const [min, max] = DURATION_BOUNDS[query.duration];
    if (min !== null) params.set("minDuration", String(min));
    if (max !== null) params.set("maxDuration", String(max));
  }
  if (query.period) params.set("since", String(periodStart(query.period)));
  if (query.sort === "random") params.set("seed", String(query.seed ?? 1));
  if (query.downloaded) params.set("downloaded", "true");
  if (query.starred) params.set("starred", "true");
  return params.toString();
}

export const fetchFeed = (query: FeedQuery) => request<Page<FeedItem>>(`/api/feed?${feedQueryString(query)}`);
export const fetchItem = (remoteId: string) => request<FeedItem>(`/api/items/${encodeURIComponent(remoteId)}`);
export const fetchHome = () => request<HomeSnapshot>("/api/home");
export const fetchSyncHealth = () => request<SyncHealth>("/api/health/sync");
export const setItemStar = (remoteId: string, starred: boolean) =>
  request<{ starred: boolean; starredAt: number | null }>(`/api/items/${encodeURIComponent(remoteId)}/star`, {
    method: starred ? "PUT" : "DELETE",
  });
export const fetchCreators = ({ search, sort = "items", cursor }: { search?: string; sort?: "items" | "recent"; cursor?: string }) => {
  const params = new URLSearchParams({ limit: "40", sort });
  if (search) params.set("search", search);
  if (cursor) params.set("cursor", cursor);
  return request<Page<Creator>>(`/api/creators?${params}`);
};
export const fetchSettings = () => request<SettingsPayload>("/api/settings");
export const updateSettings = (changes: Partial<RuntimeSettings>) =>
  request<SettingsPayload>("/api/settings", { method: "PUT", body: JSON.stringify(changes) });
export const fetchAlbums = () => request<{ items: Album[] }>("/api/albums");
export const createAlbum = (name: string) => request<Album>("/api/albums", { method: "POST", body: JSON.stringify({ name }) });
export const renameAlbum = (albumId: number, name: string) =>
  request<Album>(`/api/albums/${albumId}`, { method: "PATCH", body: JSON.stringify({ name }) });
export const deleteAlbum = (albumId: number) => request<{ deleted: boolean }>(`/api/albums/${albumId}`, { method: "DELETE" });
export const addToAlbum = (albumId: number, itemIds: string[]) =>
  request<{ added: number; album: Album }>(`/api/albums/${albumId}/items`, { method: "PUT", body: JSON.stringify({ itemIds }) });
export const removeFromAlbum = (albumId: number, itemIds: string[]) =>
  request<{ removed: number; album: Album }>(`/api/albums/${albumId}/items`, { method: "DELETE", body: JSON.stringify({ itemIds }) });
export const fetchTags = () => request<{ items: TagSummary[] }>("/api/tags");
export const setItemTags = (remoteId: string, tags: string[]) =>
  request<{ tags: string[] }>(`/api/items/${encodeURIComponent(remoteId)}/tags`, { method: "PUT", body: JSON.stringify({ tags }) });
export const setItemNote = (remoteId: string, note: string) =>
  request<{ note: string | null }>(`/api/items/${encodeURIComponent(remoteId)}/note`, { method: "PUT", body: JSON.stringify({ note }) });
export const archiveSelection = (itemIds: string[]) =>
  request<{ batch: ArchiveBatch; skipped: number }>("/api/archive/selection", { method: "POST", body: JSON.stringify({ itemIds }) });
export const fetchMissingSummary = () => request<{ missing: number; estimatedBytes: number | null }>("/api/archive/missing");
export const archiveMissing = () => request<{ batch: ArchiveBatch; skipped: number }>("/api/archive/missing", { method: "POST" });
export const bulkStar = (itemIds: string[], starred: boolean) =>
  request<{ starred: string[] }>("/api/items/bulk-star", { method: "POST", body: JSON.stringify({ itemIds, starred }) });
export const testNotifications = () =>
  request<{ results: Record<string, string> }>("/api/settings/notifications/test", { method: "POST" });
export const logout = () => request<Record<string, unknown>>("/api/session", { method: "DELETE" });
export const fetchCreator = (creatorId: string) => request<Creator>(`/api/creators/${creatorId}`);
export const refreshCreator = (creatorId: string) =>
  request<Creator>(`/api/creators/${encodeURIComponent(creatorId)}/refresh`, { method: "POST" });
export const archiveItem = (remoteId: string) =>
  request<ArchiveBatch>(`/api/archive/items/${encodeURIComponent(remoteId)}`, { method: "POST" });
export const archiveCreator = (creatorId: string) =>
  request<ArchiveBatch>(`/api/archive/creators/${encodeURIComponent(creatorId)}`, { method: "POST" });
export const archiveSource = (sourceId: string) =>
  request<ArchiveBatch>(`/api/archive/sources/${encodeURIComponent(sourceId)}`, { method: "POST" });
export const updateCreatorSubscription = (creatorId: string, enabled: boolean) =>
  request<CreatorSubscription>(`/api/creator-subscriptions/${encodeURIComponent(creatorId)}`, {
    method: "PUT",
    body: JSON.stringify({ enabled, scanIntervalSeconds: 21_600, archiveNewItems: true }),
  });
export const beginDouyinLogin = () =>
  request<LoginStatus>("/api/douyin/login", { method: "POST" });
export const getDouyinLogin = (id: string) => request<LoginStatus>(`/api/douyin/login/${id}`);
export const douyinQrUrl = (id: string) => `/api/douyin/login/${id}/qr.png`;
export const douyinStreamUrl = (id: string) => `/api/douyin/login/${id}/stream.mjpeg`;
export const submitDouyinDrag = (id: string, points: PointerPoint[]) =>
  request<LoginStatus>(`/api/douyin/login/${id}/drag`, {
    method: "POST",
    body: JSON.stringify({ points }),
  });
export const submitDouyinPointer = (id: string, event: PointerEventPayload) =>
  request<{ accepted: boolean }>(`/api/douyin/login/${id}/pointer`, {
    method: "POST",
    body: JSON.stringify(event),
  });
export const submitDouyinKey = (id: string, key: string) =>
  request<{ accepted: boolean }>(`/api/douyin/login/${id}/key`, {
    method: "POST",
    body: JSON.stringify({ key }),
  });
export const triggerSync = (fullScan = false) =>
  request<{ runId: number }>("/api/sync", {
    method: "POST",
    body: JSON.stringify({ fullScan }),
  });
