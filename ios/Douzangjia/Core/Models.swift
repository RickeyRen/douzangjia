import Foundation

// Mirrors the JSON the NAS web app already serves (web/src/app/api.ts).
// Optional wherever the server may omit a field, so a newer server never breaks decoding.

struct BootstrapStatus: Decodable {
    let configured: Bool
    let authenticated: Bool
    let douyinAuthenticated: Bool?
    let version: String?
}

struct Page<T: Decodable>: Decodable {
    let items: [T]
    let nextCursor: String?
}

struct MediaFile: Decodable, Hashable {
    let id: Int
    let index: Int
    let type: String
    let byteSize: Int?
    let mimeType: String?
    let url: String
    let posterUrl: String?

    var isVideo: Bool { type == "video" || (mimeType ?? "").hasPrefix("video/") }
}

struct LocalArchiveState: Decodable, Hashable {
    let state: String
    let readyAssets: Int
    let totalAssets: Int
    let downloadedBytes: Int
    let totalBytes: Int?
}

struct DouyinInfo: Decodable, Hashable {
    let statistics: [String: Int]?
    let durationMs: Int?
}

struct FeedItem: Decodable, Identifiable, Hashable {
    let awemeId: String
    let author: String
    let description: String
    let type: String
    let publishedAt: Int?
    let archivedAt: Int
    let coverUrl: String?
    let thumbnailUrl: String?
    var starred: Bool?
    let media: [MediaFile]
    let local: LocalArchiveState?
    let douyin: DouyinInfo?

    var id: String { awemeId }
    var isGallery: Bool { type == "gallery" }
    var isSaved: Bool { !media.isEmpty }
    var previewPath: String? { thumbnailUrl ?? coverUrl }
    var title: String {
        let text = description.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? "@\(author)" : text
    }
}

struct HomeStats: Decodable {
    let items: Int
    let videos: Int
    let galleries: Int
    let downloadedItems: Int
    let archivedBytes: Int
    let creators: Int
    let starred: Int
    let gone: Int
}

struct SyncHealth: Decodable {
    let state: String
    let lastSuccessAt: Int?
    let lastErrorCode: String?
    let intervalSeconds: Int
    let browser: String?
}

struct HomeSnapshot: Decodable {
    let stats: HomeStats
    let health: SyncHealth
    let recent: [FeedItem]
    let starred: [FeedItem]
}

struct MissingSummary: Decodable {
    let missing: Int
    let estimatedBytes: Int?
}

struct ArchiveProgressBatch: Decodable, Identifiable {
    let id: Int
    let kind: String
    let label: String
    let status: String
    let totalItems: Int
}

struct ArchiveProgressItem: Decodable, Identifiable {
    let remoteId: String
    let description: String
    let author: String
    let coverUrl: String?
    let downloadedBytes: Int
    let totalBytes: Int?
    var id: String { remoteId }
}

struct ArchiveFailure: Decodable, Identifiable {
    let remoteId: String
    let description: String
    let author: String
    let errorCode: String?
    let attempts: Int
    var id: String { remoteId }
}

struct ActiveDownload: Decodable {
    let status: String
    let batches: [ArchiveProgressBatch]
    let totalItems: Int
    let completedItems: Int
    let failedItems: Int
    let runningItems: Int
    let waitingItems: Int
    let downloadedBytes: Int
    let estimatedTotalBytes: Int?
    let speedBps: Double
    let etaSeconds: Int?
    let current: [ArchiveProgressItem]

    var isPaused: Bool { status == "paused" }
    var fraction: Double { totalItems > 0 ? Double(completedItems) / Double(totalItems) : 0 }
}

struct ArchiveProgress: Decodable {
    let active: ActiveDownload?
    let failures: [ArchiveFailure]
    let failedTotal: Int
}

struct SyncRun: Decodable, Identifiable {
    let id: Int
    let mode: String
    let status: String
    let discovered: Int
    let enqueued: Int
    let errorCode: String?
    let startedAt: Int
}

struct APIErrorBody: Decodable {
    let code: String?
    let message: String?
}

struct EmptyBody: Decodable {}
