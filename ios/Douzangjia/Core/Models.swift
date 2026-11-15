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
    let id: String?
    let nickname: String?
    let avatarUrl: String?
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
    // Owner's own organisation; optional so older servers still decode.
    var albums: [AlbumRef]?
    var tags: [String]?
    var note: String?
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

struct AlbumRef: Decodable, Hashable {
    let id: Int
    let name: String
}

struct Album: Decodable, Identifiable, Hashable {
    let id: Int
    let name: String
    let itemCount: Int
    let covers: [String]
}

struct TagCount: Decodable, Hashable {
    let tag: String
    let itemCount: Int
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

struct CreatorMonitor: Decodable {
    let libraryCreators: Int
    let checkedCreators: Int
    let cataloguedCreators: Int
    let catalogItems: Int
    let savedCovers: Int
    let consecutiveFailures: Int
}

struct VanishedPage: Decodable {
    let items: [Creator]
    let nextCursor: String?
    let counts: [String: Int]
    let monitor: CreatorMonitor?
}

struct MissingSummary: Decodable {
    let missing: Int
    let queued: Int?
    let estimatedBytes: Int?

    /// Items without media that no download is waiting on yet.
    var unqueued: Int { max(0, missing - (queued ?? 0)) }
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
    /// Optional so an older server without the field still decodes.
    let itemsPerMinute: Double?
    let etaSeconds: Int?
    let current: [ArchiveProgressItem]

    var isPaused: Bool { status == "paused" }
    /// Whole plan while a bulk download is still being queued in the background.
    let plannedItems: Int?
    let queueing: Bool?
    /// Set while Douyin hands out no fresh download links; the server retries on its own.
    let linkRefusal: LinkRefusal?

    struct LinkRefusal: Decodable {
        let refusedSince: Int
        let retryAt: Int?
    }

    var refusalNotice: String? {
        guard let linkRefusal, !isPaused else { return nil }
        guard let retryAt = linkRefusal.retryAt else { return "抖音暂时不给新的下载链接，正在确认，会自动再试。" }
        let clock = Date(timeIntervalSince1970: TimeInterval(retryAt)).formatted(date: .omitted, time: .shortened)
        return "抖音暂时不给新的下载链接，已自动放慢，\(clock) 自动再试，不用手动暂停。"
    }

    /// Items this download will cover, counting ones still being queued.
    var plannedTotal: Int { max(totalItems, plannedItems ?? 0) }
    var fraction: Double { plannedTotal > 0 ? Double(completedItems) / Double(plannedTotal) : 0 }
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

/// Backup self-check: how much of the saved archive has been confirmed intact.
struct ArchiveIntegrity: Decodable {
    let totalFiles: Int
    let verifiedFiles: Int
    /// Fast pass: seen on disk with the right size; optional for older servers.
    let presentFiles: Int?
    let allPresentSince: Int?
    let allCheckedSince: Int?
    let lastCheckedAt: Int?
    let repairingFiles: Int
    let repairedFiles: Int

    var headline: String {
        if totalFiles == 0 { return "还没有存下的文件" }
        if allCheckedSince != nil { return "全部 \(Format.integer(totalFiles)) 个文件都完好" }
        if allPresentSince != nil {
            return "全部 \(Format.integer(totalFiles)) 个文件都在，内容已核对 \(Format.integer(verifiedFiles)) 个"
        }
        return "已检查 \(Format.integer(presentFiles ?? verifiedFiles)) / \(Format.integer(totalFiles)) 个文件"
    }

    /// Follows the slow part (hashing) once every file has been seen.
    var fraction: Double {
        guard totalFiles > 0 else { return 0 }
        let done = allPresentSince != nil ? verifiedFiles : (presentFiles ?? verifiedFiles)
        return Double(done) / Double(totalFiles)
    }
}

/// Daily self-checked database copies on the NAS.
struct BackupStatus: Decodable {
    struct Copy: Decodable {
        let name: String
        let bytes: Int
        let createdAt: Int
    }

    let directory: String
    let keep: Int
    let lastError: String?
    let backups: [Copy]
}

/// A Douyin list the library is synced from (likes, a favourites folder, …).
struct LibrarySource: Decodable, Identifiable, Hashable {
    let id: String
    let kind: String
    let name: String
    let discoveredCount: Int
    let archivedCount: Int

    /// Lists worth browsing on the phone: passing feeds and music are left out.
    var browsable: Bool {
        discoveredCount > 0 && !["recommend", "watch_history", "favorite_music"].contains(kind)
    }

    var title: String {
        switch kind {
        case "favorite_video": "全部收藏"
        case "like": "喜欢"
        case "favorite_series": "收藏合集"
        case "favorite_drama": "短剧"
        case "following": "关注的人"
        case "post": "我的作品"
        case "watch_later": "稍后再看"
        case "reservation": "预约"
        default: name
        }
    }

    var systemImage: String {
        switch kind {
        case "favorite_video": "bookmark"
        case "like": "heart"
        case "favorite_series": "square.stack"
        case "favorite_drama": "film"
        case "following": "person.badge.plus"
        case "post": "video"
        case "watch_later": "clock"
        default: "folder"
        }
    }
}
