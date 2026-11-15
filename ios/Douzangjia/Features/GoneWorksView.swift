import SwiftUI

struct GoneWorksRoute: Hashable {}

/// 已在抖音消失: works Douyin deleted or hid. Whatever reached the NAS still plays here.
struct GoneWorksView: View {
    @Environment(AppModel.self) private var model
    @State private var savedOnly = false
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
                Text("抖音上已经删除或设为私密的作品。只要存到了 NAS，这里就永远能看。")
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
                Picker("范围", selection: $savedOnly) {
                    Text("全部").tag(false)
                    Text("已存到 NAS").tag(true)
                }
                .pickerStyle(.segmented)

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
                    ContentUnavailableView(
                        savedOnly ? "消失的作品里还没有存下来的" : "还没发现消失的作品",
                        systemImage: "icloud.slash",
                        description: Text(savedOnly ? "" : "抖藏家会在后台慢慢抽查每个作品是否还在抖音上，抽查到的会出现在这里。")
                    )
                }
            }
            .padding(.horizontal, Theme.pageInset)
            .padding(.bottom, 16)
        }
        .scrollIndicators(.hidden)
        .screenBackground()
        .navigationTitle("已在抖音消失")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await reload() }
        .task(id: savedOnly) { await reload() }
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
        items = model.client.cachedGoneFeed(savedOnly: savedOnly)?.items ?? []
        await loadMore(replacing: true)
    }

    private func loadMore(replacing: Bool = false) async {
        guard !loading, !exhausted || replacing else { return }
        loading = true
        let started = generation
        defer { loading = false }
        do {
            let page = try await model.client.goneFeed(cursor: replacing ? nil : cursor, savedOnly: savedOnly)
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
