import SwiftUI
import UIKit

/// Decoded thumbnails kept in memory, with the NAS responses also kept on disk
/// by URLCache, so scrolling back up or reopening the grid never refetches.
@MainActor
final class ImageStore {
    static let shared = ImageStore()
    private let memory = NSCache<NSURL, UIImage>()
    private var inflight: [URL: Task<UIImage?, Never>] = [:]

    private init() {
        memory.totalCostLimit = 96 * 1024 * 1024
    }

    func cached(_ url: URL) -> UIImage? {
        memory.object(forKey: url as NSURL)
    }

    func image(for url: URL) async -> UIImage? {
        if let hit = cached(url) { return hit }
        if let running = inflight[url] { return await running.value }
        let task = Task<UIImage?, Never> {
            // Posters on the NAS need the session cookie, which the shared
            // URLSession cookie store already carries.
            var request = URLRequest(url: url)
            request.cachePolicy = .returnCacheDataElseLoad
            guard let (data, response) = try? await URLSession.shared.data(for: request),
                  (response as? HTTPURLResponse)?.statusCode == 200,
                  let image = UIImage(data: data) else { return nil }
            return image.preparingForDisplay() ?? image
        }
        inflight[url] = task
        let image = await task.value
        inflight[url] = nil
        if let image {
            let cost = Int(image.size.width * image.size.height * image.scale * image.scale * 4)
            memory.setObject(image, forKey: url as NSURL, cost: cost)
        }
        return image
    }
}

/// Thumbnail that resolves server-relative paths.
struct RemoteImage: View {
    @Environment(AppModel.self) private var model
    let path: String?
    var contentMode: ContentMode = .fill
    var failureIcon = "photo"
    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        let url = model.client.resolve(path)
        ZStack {
            if let shown = image ?? url.flatMap({ ImageStore.shared.cached($0) }) {
                Image(uiImage: shown).resizable().aspectRatio(contentMode: contentMode)
            } else {
                Rectangle().fill(Theme.panel2)
                    .overlay {
                        if failed, !failureIcon.isEmpty { Image(systemName: failureIcon).foregroundStyle(Theme.dim) }
                    }
            }
        }
        .task(id: url) {
            guard let url else { failed = true; return }
            if let hit = ImageStore.shared.cached(url) { image = hit; return }
            let loaded = await ImageStore.shared.image(for: url)
            withAnimation(.easeOut(duration: 0.2)) {
                image = loaded
                failed = loaded == nil
            }
        }
    }
}
