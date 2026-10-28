import Foundation
import Observation

@Observable
@MainActor
final class AppModel {
    enum Phase: Equatable {
        case checking
        case signedOut
        case signedIn
    }

    static let defaultServer = "http://192.168.0.6:8099"
    private static let serverKey = "serverURL"
    private static let usernameKey = "username"

    var phase: Phase = .checking
    var serverAddress: String
    var username: String
    private(set) var client: APIClient

    init() {
        let stored = UserDefaults.standard.string(forKey: Self.serverKey) ?? Self.defaultServer
        serverAddress = stored
        username = UserDefaults.standard.string(forKey: Self.usernameKey) ?? ""
        client = APIClient(baseURL: Self.normalized(stored) ?? URL(string: Self.defaultServer)!)
    }

    /// Accepts "192.168.0.6:8099" as well as a full URL, and drops a trailing slash.
    static func normalized(_ text: String) -> URL? {
        var value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        while value.hasSuffix("/") { value.removeLast() }
        if value.isEmpty { return nil }
        if !value.contains("://") { value = "http://" + value }
        guard let url = URL(string: value), url.host != nil else { return nil }
        return url
    }

    func restore() async {
        do {
            let status = try await client.status()
            phase = status.authenticated ? .signedIn : .signedOut
        } catch {
            phase = .signedOut
        }
        #if DEBUG
        // Simulator QA: `-devUsername x -devPassword y` signs in without typing.
        let defaults = UserDefaults.standard
        if phase == .signedOut, let user = defaults.string(forKey: "devUsername"),
           let password = defaults.string(forKey: "devPassword") {
            try? await signIn(server: serverAddress, username: user, password: password)
        }
        #endif
    }

    func signIn(server: String, username: String, password: String) async throws {
        guard let url = Self.normalized(server) else {
            throw APIError(status: 0, code: "BAD_URL", message: "服务器地址格式不对，例如 192.168.0.6:8099")
        }
        let candidate = APIClient(baseURL: url)
        try await candidate.login(username: username, password: password)
        client = candidate
        serverAddress = url.absoluteString
        self.username = username
        UserDefaults.standard.set(serverAddress, forKey: Self.serverKey)
        UserDefaults.standard.set(username, forKey: Self.usernameKey)
        phase = .signedIn
    }

    func signOut() async {
        await client.logout()
        phase = .signedOut
    }

    /// Any screen that gets a 401 sends the user back to the login form.
    func handle(_ error: Error) {
        if let apiError = error as? APIError, apiError.isAuthRequired {
            phase = .signedOut
        }
    }
}
