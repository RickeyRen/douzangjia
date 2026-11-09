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

    var creators: [Creator] = []
    private var search = ""

    func reload(client: APIClient, filter: LibraryFilter, search: String = "", onError: (Error) -> Void) async {
        generation += 1
        cursor = nil
        exhausted = false
        items = []
        self.search = search
        let started = generation
        if search.isEmpty {
            creators = []
        } else {
            let found = (try? await client.searchCreators(search)) ?? []
            guard started == generation else { return }
            creators = found
        }
        await loadMore(client: client, filter: filter, onError: onError)
    }

    func loadMore(client: APIClient, filter: LibraryFilter, onError: (Error) -> Void) async {
        guard !loading, !exhausted else { return }
        loading = true
        let started = generation
        defer { loading = false }
        do {
            let page = try await client.feed(filter: filter, cursor: cursor, search: search)
            guard started == generation else { return }
            let known = Set(items.map(\.id))
            items.append(contentsOf: page.items.filter { !known.contains($0.id) })
            cursor = page.nextCursor
            exhausted = page.nextCursor == nil
            error = nil
        } catch is CancellationError {
            return
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
    @State private var search = ""
    @FocusState private var searchFocused: Bool

    private var query: String { search.trimmingCharacters(in: .whitespacesAndNewlines) }

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 6), count: 3)

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    PageTitle(text: "作品").frame(height: 46)
                    searchRow
                    chips
                    if !feed.creators.isEmpty {
                        creatorResults
                    }
                    if !feed.items.isEmpty {
                        SectionHeader(title: "作品", count: query.isEmpty ? nil : "\(feed.items.count)\(feed.loading ? "+" : "")") {
                            Label(filter == .starred ? "精选" : "最近收藏", systemImage: "arrow.up.arrow.down")
                                .labelStyle(.titleAndIcon)
                        }
                    }
                    LazyVGrid(columns: columns, spacing: 6) {
                        ForEach(Array(feed.items.enumerated()), id: \.element.id) { index, item in
                            Button {
                                player = PlayerSelection(items: feed.items, index: index)
                            } label: {
                                Color.clear
                                    .aspectRatio(3 / 4, contentMode: .fit)
                                    .overlay { MediaTile(item: item) }
                            }
                            .buttonStyle(.plain)
                            .onAppear {
                                if index >= feed.items.count - 9 {
                                    Task { await feed.loadMore(client: model.client, filter: filter, onError: model.handle) }
                                }
                            }
                        }
                    }

                    if feed.loading {
                        ProgressView().frame(maxWidth: .infinity).padding(24)
                    } else if let error = feed.error, feed.items.isEmpty {
                        ContentUnavailableView {
                            Label("读取失败", systemImage: "wifi.exclamationmark")
                        } description: {
                            Text(error)
                        } actions: {
                            Button("重试") { Task { await reload() } }
                                .buttonStyle(PrimaryButtonStyle(compact: true))
                        }
                    } else if feed.items.isEmpty && !query.isEmpty {
                        if feed.creators.isEmpty {
                            ContentUnavailableView.search(text: query)
                        }
                    } else if feed.items.isEmpty {
                        ContentUnavailableView(emptyTitle, systemImage: "tray")
                    }
                }
                .padding(.horizontal, Theme.pageInset)
                .padding(.bottom, 12)
            }
            .scrollIndicators(.hidden)
            .tabBarClearance()
            .statusBarScrim()
            .scrollDismissesKeyboard(.immediately)
            .screenBackground()
            .toolbar(.hidden, for: .navigationBar)
            .refreshable { await reload() }
            .navigationDestination(for: CreatorRoute.self) { CreatorArchiveView(creatorId: $0.id) }
            .task(id: "\(filter.rawValue)|\(query)") {
                if !query.isEmpty { try? await Task.sleep(for: .milliseconds(350)) }
                if Task.isCancelled { return }
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

    private var searchRow: some View {
        HStack(spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(Theme.muted)
                TextField("", text: $search, prompt: Text("作品描述、博主名或抖音号").foregroundStyle(Theme.dim))
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.text)
                    .tint(Theme.violet3)
                    .focused($searchFocused)
                    .submitLabel(.search)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                if !search.isEmpty {
                    Button { search = "" } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(Theme.text)
                            .frame(width: 20, height: 20)
                            .background(Theme.gray, in: Circle())
                    }
                    .accessibilityLabel("清除")
                }
            }
            .padding(.leading, 14)
            .padding(.trailing, 10)
            .frame(height: 44)
            .background(Theme.panel, in: Capsule())
            .overlay(
                Capsule().strokeBorder(searchFocused ? Theme.violet2 : Theme.line2, lineWidth: searchFocused ? 1.5 : 1)
            )
            .background(
                Capsule().stroke(Theme.violet.opacity(searchFocused ? 0.18 : 0), lineWidth: 8)
            )
            .animation(.easeOut(duration: 0.15), value: searchFocused)
            if searchFocused || !search.isEmpty {
                Button("取消") {
                    search = ""
                    searchFocused = false
                }
                .font(.system(size: 14))
                .foregroundStyle(Theme.violet4)
                .transition(.move(edge: .trailing).combined(with: .opacity))
            }
        }
        .animation(.easeOut(duration: 0.2), value: searchFocused || !search.isEmpty)
        .padding(.top, 4)
    }

    private var chips: some View {
        HStack(spacing: 6) {
            ForEach(LibraryFilter.allCases) { option in
                let on = option == filter
                Button { filter = option } label: {
                    Text(option.title)
                        .font(.system(size: 12.5, weight: on ? .semibold : .regular))
                        .foregroundStyle(on ? .white : Theme.muted)
                        .lineLimit(1)
                        .padding(.horizontal, 13)
                        .frame(height: 30)
                        .background(on ? Theme.violet : Theme.panel, in: Capsule())
                        .overlay(Capsule().strokeBorder(on ? .clear : Theme.line, lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
            Spacer(minLength: 0)
        }
        .padding(.top, 6)
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
        await feed.reload(client: model.client, filter: filter, search: query, onError: model.handle)
    }

    private var creatorResults: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionHeader(title: "博主", count: "\(feed.creators.count)")
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
                ForEach(feed.creators) { creator in
                    NavigationLink(value: CreatorRoute(id: creator.id)) {
                        HStack(spacing: 10) {
                            CreatorAvatar(path: creator.avatarUrl, size: 42)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(highlighted(creator.nickname))
                                    .font(.system(size: 13.5, weight: .semibold))
                                    .foregroundStyle(Theme.text)
                                    .lineLimit(1)
                                Text("\(Format.integer(creator.knownItemCount)) 个作品")
                                    .font(.system(size: 11.5))
                                    .foregroundStyle(Theme.muted)
                                    .lineLimit(1)
                            }
                            Spacer(minLength: 0)
                            Image(systemName: "chevron.right")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(Theme.dim)
                        }
                        .card(radius: Theme.radiusInner, padding: EdgeInsets(top: 10, leading: 10, bottom: 10, trailing: 10))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    /// Paints the searched text violet inside a creator name.
    private func highlighted(_ name: String) -> AttributedString {
        var text = AttributedString(name)
        if !query.isEmpty, let range = text.range(of: query, options: .caseInsensitive) {
            text[range].foregroundColor = Theme.violet4
        }
        return text
    }
}
