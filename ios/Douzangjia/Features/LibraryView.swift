import SwiftUI

@Observable
@MainActor
final class LibraryFeed {
    var items: [FeedItem] = []
    var loading = false
    var error: String?
    private var cursor: String?
    private var exhausted = false
    private var generation = 0

    func reload(client: APIClient, filter: LibraryFilter, onError: (Error) -> Void) async {
        generation += 1
        cursor = nil
        exhausted = false
        items = []
        await loadMore(client: client, filter: filter, onError: onError)
    }

    func loadMore(client: APIClient, filter: LibraryFilter, onError: (Error) -> Void) async {
        guard !loading, !exhausted else { return }
        loading = true
        let started = generation
        defer { loading = false }
        do {
            let page = try await client.feed(filter: filter, cursor: cursor)
            guard started == generation else { return }
            let known = Set(items.map(\.id))
            items.append(contentsOf: page.items.filter { !known.contains($0.id) })
            cursor = page.nextCursor
            exhausted = page.nextCursor == nil
            error = nil
        } catch {
            onError(error)
            self.error = error.localizedDescription
        }
    }

    func update(_ item: FeedItem) {
        if let index = items.firstIndex(where: { $0.id == item.id }) { items[index] = item }
    }
}

struct LibraryView: View {
    @Environment(AppModel.self) private var model
    @State private var filter: LibraryFilter = LibraryView.initialFilter
    @State private var feed = LibraryFeed()
    @State private var player: PlayerSelection?

    private let columns = [GridItem(.adaptive(minimum: 110), spacing: 3)]

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVGrid(columns: columns, spacing: 3) {
                    ForEach(Array(feed.items.enumerated()), id: \.element.id) { index, item in
                        Button {
                            player = PlayerSelection(items: feed.items, index: index)
                        } label: {
                            MediaTile(item: item)
                                .aspectRatio(3 / 4, contentMode: .fit)
                        }
                        .buttonStyle(.plain)
                        .onAppear {
                            if index >= feed.items.count - 9 {
                                Task { await feed.loadMore(client: model.client, filter: filter, onError: model.handle) }
                            }
                        }
                    }
                }
                .padding(.horizontal, 3)

                if feed.loading {
                    ProgressView().padding(24)
                } else if let error = feed.error, feed.items.isEmpty {
                    ContentUnavailableView {
                        Label("读取失败", systemImage: "wifi.exclamationmark")
                    } description: {
                        Text(error)
                    } actions: {
                        Button("重试") { Task { await reload() } }
                    }
                } else if feed.items.isEmpty {
                    ContentUnavailableView(emptyTitle, systemImage: "tray")
                }
            }
            .navigationTitle("作品")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Picker("筛选", selection: $filter) {
                        ForEach(LibraryFilter.allCases) { Text($0.title).tag($0) }
                    }
                    .pickerStyle(.segmented)
                    .frame(maxWidth: 320)
                }
            }
            .refreshable { await reload() }
            .task(id: filter) {
                await reload()
                #if DEBUG
                // Simulator QA: `-devOpenPlayer N` opens the player on item N.
                let index = UserDefaults.standard.integer(forKey: "devOpenPlayer") - 1
                if player == nil, feed.items.indices.contains(index) {
                    player = PlayerSelection(items: feed.items, index: index)
                }
                #endif
            }
            .fullScreenCover(item: $player) { selection in
                PlayerView(items: selection.items, startIndex: selection.index) { feed.update($0) }
            }
        }
    }

    private static var initialFilter: LibraryFilter {
        #if DEBUG
        return UserDefaults.standard.string(forKey: "devFilter").flatMap(LibraryFilter.init(rawValue:)) ?? .all
        #else
        return .all
        #endif
    }

    private var emptyTitle: String {
        switch filter {
        case .all: "还没有收藏"
        case .saved: "还没有存到 NAS 的作品"
        case .starred: "还没有精选，在播放时点星标加入"
        }
    }

    private func reload() async {
        await feed.reload(client: model.client, filter: filter, onError: model.handle)
    }
}
