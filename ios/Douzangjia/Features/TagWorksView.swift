import SwiftUI

struct TagRoute: Hashable { let tag: String }

/// Every work carrying one of the owner's own tags.
struct TagWorksView: View {
    let tag: String
    @Environment(AppModel.self) private var model
    @State private var items: [FeedItem] = []
    @State private var cursor: String?
    @State private var exhausted = false
    @State private var loading = false
    @State private var loadError: String?
    @State private var generation = 0
    @State private var player: PlayerSelection?

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 6), count: 3)

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                LazyVGrid(columns: columns, spacing: 6) {
                    ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
                        Button {
                            player = PlayerSelection(items: items, index: index)
                        } label: {
                            Color.clear
                                .aspectRatio(3 / 4, contentMode: .fit)
                                .overlay { MediaTile(item: item) }
                        }
                        .buttonStyle(.plain)
                        .onAppear {
                            if index >= items.count - 9 { Task { await loadMore() } }
                        }
                    }
                }

                if loading {
                    ProgressView().frame(maxWidth: .infinity).padding(24)
                } else if let loadError, items.isEmpty {
                    ContentUnavailableView {
                        Label("读取失败", systemImage: "wifi.exclamationmark")
                    } description: {
                        Text(loadError)
                    } actions: {
                        Button("重试") { Task { await reload() } }
                            .buttonStyle(.glassProminent)
                            .tint(Theme.violet2)
                    }
                } else if items.isEmpty {
                    ContentUnavailableView("这个标签下没有作品了", systemImage: "number",
                                           description: Text("标签可能已经从作品上去掉了，下拉刷新看看。"))
                }
            }
            .padding(.horizontal, Theme.pageInset)
            .padding(.bottom, 16)
        }
        .scrollIndicators(.hidden)
        .screenBackground()
        .navigationTitle("#\(tag)")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await reload() }
        .task { await reload() }
        .fullScreenCover(item: $player) { selection in
            PlayerView(items: selection.items, startIndex: selection.index) { changed in
                if let index = items.firstIndex(where: { $0.id == changed.id }) { items[index] = changed }
            }
        }
    }

    private func reload() async {
        generation += 1
        cursor = nil
        exhausted = false
        // Last answer first, so the grid is not blank while the NAS thinks.
        items = model.client.cachedTagFeed(tag)?.items ?? []
        await loadMore(replacing: true)
    }

    private func loadMore(replacing: Bool = false) async {
        guard !loading, !exhausted || replacing else { return }
        loading = true
        let started = generation
        defer { loading = false }
        do {
            let page = try await model.client.tagFeed(tag, cursor: replacing ? nil : cursor)
            guard started == generation else { return }
            if replacing {
                items = page.items
            } else {
                let known = Set(items.map(\.id))
                items.append(contentsOf: page.items.filter { !known.contains($0.id) })
            }
            cursor = page.nextCursor
            exhausted = page.nextCursor == nil
            loadError = nil
        } catch is CancellationError {
            return
        } catch {
            model.handle(error)
            loadError = error.localizedDescription
        }
    }
}
