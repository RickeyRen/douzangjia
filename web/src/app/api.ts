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
  kind: "item" | "source" | "creator";
  targetId: string;
  status: string;
  discoveredCount?: number;
  completedCount?: number;
  failedCount?: number;
  downloadedBytes?: number;
  totalBytes?: number | null;
  errorCode?: string | null;
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
export const setupAdmin = (password: string) =>
  request<{ configured: boolean }>("/api/setup", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
export const loginAdmin = (password: string) =>
  request<{ authenticated: boolean }>("/api/session", {
    method: "POST",
    body: JSON.stringify({ password }),
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
export const fetchFeed = ({
  sourceId,
  collectionId,
  author,
  creatorId,
  search,
  cursor,
}: {
  sourceId?: string;
  collectionId?: string;
  author?: string;
  creatorId?: string;
  search?: string;
  cursor?: string;
}) => {
  const query = new URLSearchParams({ limit: "20" });
  if (creatorId) query.set("creatorId", creatorId);
  if (sourceId) query.set("sourceId", sourceId);
  if (collectionId) query.set("collectionId", collectionId);
  if (author) query.set("author", author);
  if (search && !creatorId) query.set("search", search);
  if (cursor) query.set("cursor", cursor);
  const path = creatorId || sourceId ? "/api/library/feed" : "/api/feed";
  return request<{ items: FeedItem[]; nextCursor: string | null }>(`${path}?${query}`);
};
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
