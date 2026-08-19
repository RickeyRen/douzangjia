export type Collection = {
  id: string;
  name: string;
  itemCount: number;
  lastSeenAt: number;
};

export type MediaFile = {
  id: number;
  index: number;
  type: string;
  byteSize: number | null;
  mimeType: string | null;
  url: string;
};

export type FeedItem = {
  awemeId: string;
  author: string;
  description: string;
  type: "video" | "gallery";
  publishedAt: number | null;
  archivedAt: number;
  collections: Array<{ id: string; name: string }>;
  media: MediaFile[];
  local: LocalArchiveState;
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
export const fetchJobs = () => request<DownloadSnapshot>("/api/jobs?limit=50");
export const fetchSyncRuns = () => request<{ items: SyncRun[] }>("/api/sync/runs?limit=20");
export const fetchFeed = ({
  collectionId,
  author,
  search,
  cursor,
}: {
  collectionId?: string;
  author?: string;
  search?: string;
  cursor?: string;
}) => {
  const query = new URLSearchParams({ limit: "20" });
  if (collectionId) query.set("collectionId", collectionId);
  if (author) query.set("author", author);
  if (search) query.set("search", search);
  if (cursor) query.set("cursor", cursor);
  return request<{ items: FeedItem[]; nextCursor: string | null }>(`/api/feed?${query}`);
};
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
