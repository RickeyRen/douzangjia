import CryptoKit
import Foundation

/// Last good answer for each read endpoint, kept on disk so every screen can
/// show what it had immediately and refresh in the background. The NAS disk
/// is often busy; a cold page took six seconds and the app showed a spinner
/// on every launch.
final class ResponseCache {
    private let directory: URL
    private let queue = DispatchQueue(label: "douzangjia.response-cache", qos: .utility)

    init(server: URL) {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        let host = (server.host() ?? "nas") + "-" + String(server.port ?? 80)
        directory = base.appending(path: "responses/\(host)", directoryHint: .isDirectory)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    func data(for url: URL) -> Data? {
        try? Data(contentsOf: file(for: url))
    }

    func store(_ data: Data, for url: URL) {
        let target = file(for: url)
        queue.async { try? data.write(to: target, options: .atomic) }
    }

    func clear() {
        try? FileManager.default.removeItem(at: directory)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    private func file(for url: URL) -> URL {
        let digest = SHA256.hash(data: Data(url.absoluteString.utf8))
        let name = digest.prefix(12).map { String(format: "%02x", $0) }.joined()
        return directory.appending(path: "\(name).json")
    }
}
