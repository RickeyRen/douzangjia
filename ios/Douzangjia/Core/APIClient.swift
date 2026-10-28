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

    init(baseURL: URL) {
        self.baseURL = baseURL
        let configuration = URLSessionConfiguration.default
        configuration.httpCookieStorage = .shared
        configuration.httpShouldSetCookies = true
        configuration.timeoutIntervalForRequest = 20
        session = URLSession(configuration: configuration)
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

    func feed(filter: LibraryFilter, cursor: String?) async throws -> Page<FeedItem> {
        var query = [URLQueryItem(name: "limit", value: "30")]
        switch filter {
        case .all: break
        case .saved: query.append(URLQueryItem(name: "downloaded", value: "true"))
        case .starred: query.append(URLQueryItem(name: "starred", value: "true"))
        }
        if let cursor { query.append(URLQueryItem(name: "cursor", value: cursor)) }
        return try await get("/api/feed", query: query)
    }

    func setStar(_ itemId: String, starred: Bool) async throws {
        let _: EmptyBody = try await send(starred ? "PUT" : "DELETE", "/api/items/\(itemId)/star")
    }

    func archiveItem(_ itemId: String) async throws {
        let _: EmptyBody = try await send("POST", "/api/archive/items/\(itemId)")
    }

    func missingSummary() async throws -> MissingSummary { try await get("/api/archive/missing") }

    func archiveMissing() async throws {
        let _: EmptyBody = try await send("POST", "/api/archive/missing")
    }

    func progress() async throws -> ArchiveProgress { try await get("/api/archive/progress") }

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

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        var components = URLComponents(url: baseURL.appending(path: path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { components.queryItems = query }
        return try await perform(URLRequest(url: components.url!))
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

    private func perform<T: Decodable>(_ request: URLRequest) async throws -> T {
        var request = request
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError(status: 0, code: "NETWORK", message: "连不上 NAS，请确认手机和 NAS 在同一网络，或检查服务器地址。")
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let body = try? decoder.decode(APIErrorBody.self, from: data)
            throw APIError(status: status, code: body?.code ?? "HTTP_\(status)", message: body?.message ?? "请求失败（\(status)）")
        }
        if T.self == EmptyBody.self { return EmptyBody() as! T }
        do {
            return try decoder.decode(T.self, from: data)
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
