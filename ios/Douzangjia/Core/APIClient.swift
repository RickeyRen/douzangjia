import Foundation

struct APIError: LocalizedError {
    let status: Int
    let code: String
    let message: String

    var errorDescription: String? { message }
    var isAuthRequired: Bool { status == 401 }
}

/// Talks to the NAS with the same cookie session the web app uses.
/// The session cookie lives in the shared cookie store, so images and the
/// player (which is handed the cookies explicitly) are authorised too.
final class APIClient {
    let baseURL: URL
    private let session: URLSession
    private let decoder = JSONDecoder()
    private let cache: ResponseCache

    init(baseURL: URL) {
        self.baseURL = baseURL
        let configuration = URLSessionConfiguration.default
        configuration.httpCookieStorage = .shared
        configuration.httpShouldSetCookies = true
        // A busy NAS can take a while on the home page; give it room before giving up.
        configuration.timeoutIntervalForRequest = 45
        session = URLSession(configuration: configuration)
        cache = ResponseCache(server: baseURL)
    }

    /// Resolves the relative paths the API returns (e.g. `/api/media/12`).
    func resolve(_ path: String?) -> URL? {
        guard let path, !path.isEmpty else { return nil }
        if path.hasPrefix("http://") || path.hasPrefix("https://") { return URL(string: path) }
        return URL(string: path, relativeTo: baseURL)?.absoluteURL
    }

    var cookies: [HTTPCookie] { HTTPCookieStorage.shared.cookies(for: baseURL) ?? [] }

    func clearCookies() {
        for cookie in cookies { HTTPCookieStorage.shared.deleteCookie(cookie) }
        cache.clear()
    }

    // MARK: Last good answers (shown at once while a fresh request runs)

    func cachedHome() -> HomeSnapshot? { cached("/api/home") }
    func cachedMissingSummary() -> MissingSummary? { cached("/api/archive/missing") }
    func cachedSyncHealth() -> SyncHealth? { cached("/api/health/sync") }
    func cachedSyncRuns() -> [SyncRun]? {
        let page: Page<SyncRun>? = cached("/api/sync/runs", query: [URLQueryItem(name: "limit", value: "50")])
        return page?.items
    }
    func cachedIntegrity() -> ArchiveIntegrity? { cached("/api/archive/integrity") }
    func cachedFeed(filter: LibraryFilter, sourceId: String? = nil, options: FeedOptions = FeedOptions()) -> Page<FeedItem>? {
        cached("/api/feed", query: feedQuery(filter: filter, cursor: nil, search: "", sourceId: sourceId, options: options))
    }
    func cachedLibrarySources() -> [LibrarySource]? {
        let page: Page<LibrarySource>? = cached("/api/library/sources")
        return page?.items
    }
    func cachedVanished(sort: String) -> VanishedPage? {
        cached("/api/creators/vanished", query: vanishedQuery(cursor: nil, search: "", sort: sort))
    }

    private func cached<T: Decodable>(_ path: String, query: [URLQueryItem] = []) -> T? {
        guard let data = cache.data(for: url(path, query: query)) else { return nil }
        return try? decoder.decode(T.self, from: data)
    }

    // MARK: Endpoints

    func status() async throws -> BootstrapStatus { try await get("/api/status") }

    func login(username: String, password: String) async throws {
        let _: EmptyBody = try await send("POST", "/api/session", body: ["username": username, "password": password])
    }

    func logout() async {
        let _: EmptyBody? = try? await send("DELETE", "/api/session")
        clearCookies()
    }

    func home() async throws -> HomeSnapshot { try await get("/api/home") }

    func feed(filter: LibraryFilter, cursor: String?, search: String = "", sourceId: String? = nil, options: FeedOptions = FeedOptions()) async throws -> Page<FeedItem> {
        try await get("/api/feed", query: feedQuery(filter: filter, cursor: cursor, search: search, sourceId: sourceId, options: options))
    }

    func librarySources() async throws -> [LibrarySource] {
        let page: Page<LibrarySource> = try await get("/api/library/sources")
        return page.items
    }

    private func feedQuery(filter: LibraryFilter, cursor: String?, search: String, sourceId: String? = nil, options: FeedOptions = FeedOptions()) -> [URLQueryItem] {
        var query = [URLQueryItem(name: "limit", value: "30")]
        query += options.queryItems
        if let sourceId { query.append(URLQueryItem(name: "sourceId", value: sourceId)) }
        if !search.isEmpty { query.append(URLQueryItem(name: "search", value: search)) }
        switch filter {
        case .all: break
        case .saved: query.append(URLQueryItem(name: "downloaded", value: "true"))
        case .starred: query.append(URLQueryItem(name: "starred", value: "true"))
        }
        if let cursor { query.append(URLQueryItem(name: "cursor", value: cursor)) }
        return query
    }

    /// Works Douyin no longer shows (deleted or made private), newest first.
    func goneFeed(cursor: String?, savedOnly: Bool) async throws -> Page<FeedItem> {
        try await get("/api/feed", query: goneQuery(cursor: cursor, savedOnly: savedOnly))
    }
    func cachedGoneFeed(savedOnly: Bool) -> Page<FeedItem>? {
        cached("/api/feed", query: goneQuery(cursor: nil, savedOnly: savedOnly))
    }
    private func goneQuery(cursor: String?, savedOnly: Bool) -> [URLQueryItem] {
        var query = [URLQueryItem(name: "limit", value: "30"), URLQueryItem(name: "remote", value: "deleted,private")]
        if savedOnly { query.append(URLQueryItem(name: "downloaded", value: "true")) }
        if let cursor { query.append(URLQueryItem(name: "cursor", value: cursor)) }
        return query
    }

    func creatorFeed(_ creatorId: String, cursor: String?) async throws -> Page<FeedItem> {
        var query = [URLQueryItem(name: "limit", value: "30"), URLQueryItem(name: "creatorId", value: creatorId),
                     URLQueryItem(name: "sort", value: "published")]
        if let cursor { query.append(URLQueryItem(name: "cursor", value: cursor)) }
        return try await get("/api/feed", query: query)
    }

    func vanishedCreators(cursor: String?, search: String = "", sort: String = "recent") async throws -> VanishedPage {
        try await get("/api/creators/vanished", query: vanishedQuery(cursor: cursor, search: search, sort: sort))
    }

    private func vanishedQuery(cursor: String?, search: String, sort: String) -> [URLQueryItem] {
        var query = [URLQueryItem(name: "limit", value: "60"), URLQueryItem(name: "sort", value: sort)]
        if !search.isEmpty { query.append(URLQueryItem(name: "search", value: search)) }
        if let cursor { query.append(URLQueryItem(name: "cursor", value: cursor)) }
        return query
    }

    /// Every creator in the library; sort is "items" (most works) or "recent".
    func creators(search: String, sort: String, cursor: String?) async throws -> Page<Creator> {
        try await get("/api/creators", query: creatorsQuery(search: search, sort: sort, cursor: cursor))
    }
    func cachedCreators(sort: String) -> Page<Creator>? {
        cached("/api/creators", query: creatorsQuery(search: "", sort: sort, cursor: nil))
    }
    private func creatorsQuery(search: String, sort: String, cursor: String?) -> [URLQueryItem] {
        var query = [URLQueryItem(name: "limit", value: "40"), URLQueryItem(name: "sort", value: sort)]
        if !search.isEmpty { query.append(URLQueryItem(name: "search", value: search)) }
        if let cursor { query.append(URLQueryItem(name: "cursor", value: cursor)) }
        return query
    }

    func searchCreators(_ search: String) async throws -> [Creator] {
        let page: Page<Creator> = try await get(
            "/api/creators",
            query: [URLQueryItem(name: "search", value: search), URLQueryItem(name: "sort", value: "items"),
                    URLQueryItem(name: "limit", value: "20")]
        )
        return page.items
    }

    func creator(_ creatorId: String) async throws -> Creator { try await get("/api/creators/\(creatorId)") }

    func recheckCreator(_ creatorId: String) async throws -> Creator {
        try await send("POST", "/api/creators/\(creatorId)/archive-check")
    }

    func archiveCreator(_ creatorId: String) async throws {
        let _: EmptyBody = try await send("POST", "/api/archive/creators/\(creatorId)")
    }

    func setStar(_ itemId: String, starred: Bool) async throws {
        let _: EmptyBody = try await send(starred ? "PUT" : "DELETE", "/api/items/\(itemId)/star")
    }

    func albums() async throws -> [Album] {
        let page: Page<Album> = try await get("/api/albums")
        return page.items
    }

    func cachedAlbums() -> [Album]? {
        let page: Page<Album>? = cached("/api/albums")
        return page?.items
    }

    func albumFeed(_ albumId: Int, cursor: String?) async throws -> Page<FeedItem> {
        var query = [URLQueryItem(name: "limit", value: "30"), URLQueryItem(name: "albumId", value: String(albumId))]
        if let cursor { query.append(URLQueryItem(name: "cursor", value: cursor)) }
        return try await get("/api/feed", query: query)
    }

    func renameAlbum(_ albumId: Int, to name: String) async throws -> Album {
        try await send("PATCH", "/api/albums/\(albumId)", body: ["name": name])
    }

    func deleteAlbum(_ albumId: Int) async throws {
        let _: EmptyBody = try await send("DELETE", "/api/albums/\(albumId)")
    }

    func createAlbum(_ name: String) async throws -> Album {
        try await send("POST", "/api/albums", body: ["name": name])
    }

    func setAlbum(_ albumId: Int, contains itemId: String, _ contains: Bool) async throws {
        let _: EmptyBody = try await send(contains ? "PUT" : "DELETE", "/api/albums/\(albumId)/items", body: ["itemIds": [itemId]])
    }

    func tags() async throws -> [TagCount] {
        let page: Page<TagCount> = try await get("/api/tags")
        return page.items
    }

    func setTags(_ itemId: String, tags: [String]) async throws -> [String] {
        struct Result: Decodable { let tags: [String] }
        let result: Result = try await send("PUT", "/api/items/\(itemId)/tags", body: ["tags": tags])
        return result.tags
    }

    func setNote(_ itemId: String, note: String) async throws -> String? {
        struct Result: Decodable { let note: String? }
        let result: Result = try await send("PUT", "/api/items/\(itemId)/note", body: ["note": note])
        return result.note
    }

    /// Where a long video was left, on any device; nil starts from the top.
    func playback(_ itemId: String) async throws -> Int? {
        struct Result: Decodable { let positionMs: Int? }
        let result: Result = try await send("GET", "/api/items/\(itemId)/playback")
        return result.positionMs
    }

    func savePlayback(_ itemId: String, positionMs: Int, durationMs: Int) async throws {
        struct Result: Decodable { let positionMs: Int? }
        let _: Result = try await send(
            "PUT", "/api/items/\(itemId)/playback",
            body: ["positionMs": positionMs, "durationMs": durationMs]
        )
    }

    func archiveItem(_ itemId: String) async throws {
        let _: EmptyBody = try await send("POST", "/api/archive/items/\(itemId)")
    }

    func missingSummary() async throws -> MissingSummary { try await get("/api/archive/missing") }

    struct MissingQueued: Decodable {
        struct Batch: Decodable { let totalItems: Int }
        let batch: Batch
        let skipped: Int
        let queueing: Bool?
    }

    func archiveMissing() async throws -> MissingQueued {
        try await send("POST", "/api/archive/missing")
    }

    func progress() async throws -> ArchiveProgress { try await get("/api/archive/progress") }

    func integrity() async throws -> ArchiveIntegrity { try await get("/api/archive/integrity") }

    func serverSettings() async throws -> ServerSettings { try await get("/api/settings") }

    func updateSettings(_ changes: [String: Any]) async throws -> ServerSettings {
        try await send("PUT", "/api/settings", body: changes)
    }

    /// Per channel: "ok" or why it failed.
    func testNotifications() async throws -> [String: String] {
        struct Report: Decodable { let results: [String: String] }
        let report: Report = try await send("POST", "/api/settings/notifications/test")
        return report.results
    }

    /// Copies one archived file to a temporary file named `name`, ready to share.
    func downloadFile(_ url: URL, named name: String) async throws -> URL {
        let (temporary, response): (URL, URLResponse)
        do {
            (temporary, response) = try await session.download(from: url)
        } catch let error as URLError where error.code == .cancelled {
            throw CancellationError()
        } catch {
            throw APIError(status: 0, code: "NETWORK", message: "从 NAS 取文件失败，请确认手机和 NAS 在同一网络。")
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            throw APIError(status: status, code: "HTTP_\(status)", message: "NAS 上读不到这个文件（\(status)）")
        }
        let folder = FileManager.default.temporaryDirectory.appending(path: "share-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let target = folder.appending(path: name)
        try FileManager.default.moveItem(at: temporary, to: target)
        return target
    }

    func storage() async throws -> StorageUsage { try await get("/api/storage") }

    func review() async throws -> ReviewResponse { try await get("/api/review") }
    func cachedReview() -> CollectionReview? {
        if case .ready(let review)? = cached("/api/review") as ReviewResponse? { return review }
        return nil
    }

    func backupStatus() async throws -> BackupStatus { try await get("/api/backup/status") }

    func backupNow() async throws -> BackupStatus { try await send("POST", "/api/backup/now") }

    func controlBatch(_ batchId: Int, action: String) async throws {
        let _: EmptyBody = try await send("POST", "/api/archive/batches/\(batchId)/\(action)")
    }

    func retryFailed() async throws -> Int {
        struct Result: Decodable { let retried: Int }
        let result: Result = try await send("POST", "/api/archive/retry-failed")
        return result.retried
    }

    func syncHealth() async throws -> SyncHealth { try await get("/api/health/sync") }

    func syncRuns() async throws -> [SyncRun] {
        let page: Page<SyncRun> = try await get("/api/sync/runs", query: [URLQueryItem(name: "limit", value: "50")])
        return page.items
    }

    func triggerSync() async throws {
        let _: EmptyBody = try await send("POST", "/api/sync", body: ["fullScan": false])
    }

    // MARK: Transport

    private func url(_ path: String, query: [URLQueryItem]) -> URL {
        var components = URLComponents(url: baseURL.appending(path: path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { components.queryItems = query }
        return components.url!
    }

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        let target = url(path, query: query)
        return try await perform(URLRequest(url: target), cacheAs: target)
    }

    private func send<T: Decodable>(_ method: String, _ path: String, body: [String: Any]? = nil) async throws -> T {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = method
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        // The server rejects mutations without the CSRF cookie echoed as a header.
        if let csrf = cookies.first(where: { $0.name == "archive_csrf" })?.value {
            request.setValue(csrf, forHTTPHeaderField: "X-CSRF-Token")
        }
        return try await perform(request)
    }

    private func perform<T: Decodable>(_ request: URLRequest, cacheAs cacheURL: URL? = nil) async throws -> T {
        var request = request
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError where error.code == .timedOut {
            throw APIError(status: 0, code: "TIMEOUT", message: "NAS 响应太慢，等了 45 秒还没回应，可能正忙。稍后下拉重试。")
        } catch let error as URLError where error.code == .cancelled {
            throw CancellationError()
        } catch {
            let host = baseURL.host() ?? baseURL.absoluteString
            throw APIError(status: 0, code: "NETWORK", message: "连不上 NAS（\(host)），请确认手机和 NAS 在同一网络，并在 设置 › 抖藏家 里打开“本地网络”。")
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let body = try? decoder.decode(APIErrorBody.self, from: data)
            throw APIError(status: status, code: body?.code ?? "HTTP_\(status)", message: body?.message ?? "请求失败（\(status)）")
        }
        if T.self == EmptyBody.self { return EmptyBody() as! T }
        do {
            let value = try decoder.decode(T.self, from: data)
            if let cacheURL { cache.store(data, for: cacheURL) }
            return value
        } catch {
            throw APIError(status: status, code: "DECODE", message: "NAS 返回的数据看不懂，可能需要升级 App 或服务器。")
        }
    }
}

enum LibraryFilter: String, CaseIterable, Identifiable {
    case all, saved, starred
    var id: String { rawValue }
    var title: String {
        switch self {
        case .all: "全部"
        case .saved: "已存到 NAS"
        case .starred: "精选"
        }
    }
}

/// Sort and narrowing on top of 全部 / 已存 / 精选, the same choices the web offers.
struct FeedOptions: Hashable {
    enum Sort: String, CaseIterable { case standard, published, random }
    enum Kind: String, CaseIterable { case all, video, gallery }
    enum Length: String, CaseIterable { case all, short, medium, long }

    var sort: Sort = .standard
    var kind: Kind = .all
    var length: Length = .all
    /// Keeps a random order stable while paging; a new one reshuffles.
    var seed = 1

    var isNarrowed: Bool { kind != .all || length != .all }

    var queryItems: [URLQueryItem] {
        var items: [URLQueryItem] = []
        switch sort {
        case .standard: break
        case .published: items.append(URLQueryItem(name: "sort", value: "published"))
        case .random:
            items.append(URLQueryItem(name: "sort", value: "random"))
            items.append(URLQueryItem(name: "seed", value: String(seed)))
        }
        if kind != .all { items.append(URLQueryItem(name: "type", value: kind.rawValue)) }
        // Galleries have no length; the bucket only narrows videos.
        if kind != .gallery {
            switch length {
            case .all: break
            case .short: items.append(URLQueryItem(name: "maxDuration", value: "60"))
            case .medium:
                items.append(URLQueryItem(name: "minDuration", value: "60"))
                items.append(URLQueryItem(name: "maxDuration", value: "300"))
            case .long: items.append(URLQueryItem(name: "minDuration", value: "300"))
            }
        }
        return items
    }
}

extension FeedOptions.Kind {
    var title: String {
        switch self {
        case .all: "全部类型"
        case .video: "视频"
        case .gallery: "图集"
        }
    }
}

extension FeedOptions.Length {
    var title: String {
        switch self {
        case .all: "任意时长"
        case .short: "1 分钟内"
        case .medium: "1–5 分钟"
        case .long: "5 分钟以上"
        }
    }
}
