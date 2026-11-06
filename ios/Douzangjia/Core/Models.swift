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

struct FeedCreator: Decodable, Hashable {
    let archiveStatus: CreatorArchiveStatus?
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
    let creator: FeedCreator?

    var id: String { awemeId }
    /// The video was never saved and the creator's account can no longer serve it.
    var videoIsLost: Bool {
        !isSaved && (creator?.archiveStatus == .banned || creator?.archiveStatus == .vanished)
    }
    var videoIsAtRisk: Bool {
        !isSaved && (creator?.archiveStatus == .reset || creator?.archiveStatus == .deactivated)
    }
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
    let vanishedCreators: Int?
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
    let vanishedCreators: [VanishedCreatorTile]?
}

struct VanishedCreatorTile: Decodable, Identifiable, Hashable {
    let id: String
    let nickname: String
    let uniqueId: String?
    let avatarUrl: String?
    let status: String
    let since: Int?
    let itemCount: Int
}

/// How Douyin has treated a creator; "active" means nothing happened.
enum CreatorArchiveStatus: String, Decodable {
    case active, reset, deactivated, banned, vanished

    var label: String {
        switch self {
        case .active: "正常"
        case .reset: "资料被重置"
        case .deactivated: "已注销"
        case .banned: "已封禁"
        case .vanished: "作品已清空"
        }
    }

    var hint: String {
        switch self {
        case .active: ""
        case .reset: "抖音把昵称换成了一串数字、头像换成了默认头像，通常是违规后被处理，作品可能很快消失。"
        case .deactivated: "账号已经注销，抖音上只剩“该用户已注销”。"
        case .banned: "抖音上已经打不开这个账号。"
        case .vanished: "账号还在，但公开作品已经全部消失。"
        }
    }
}

struct CreatorSnapshot: Decodable, Identifiable, Hashable {
    let id: Int
    let nickname: String
    let uniqueId: String?
    let signature: String?
    let avatarUrl: String?
    let coverUrl: String?
    let followerCount: Int?
    let followingCount: Int?
    let totalFavorited: Int?
    let postCount: Int?
    let ipLocation: String?
    let degraded: Bool
    let firstSeenAt: Int
    let lastSeenAt: Int
}

struct CreatorArchive: Decodable, Hashable {
    let status: CreatorArchiveStatus
    let since: Int?
    let currentNickname: String
    let preserved: CreatorSnapshot?
    let history: [CreatorSnapshot]?
}

struct Creator: Decodable, Identifiable, Hashable {
    let id: String
    let nickname: String
    let uniqueId: String?
    let avatarUrl: String?
    let followerCount: Int?
    let postCount: Int?
    let knownItemCount: Int
    let archivedItemCount: Int
    let lastSeenAt: Int
    let signature: String?
    let followingCount: Int?
    let totalFavorited: Int?
    let ipLocation: String?
    let archive: CreatorArchive?
}

struct VanishedPage: Decodable {
    let items: [Creator]
    let nextCursor: String?
    let counts: [String: Int]
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
