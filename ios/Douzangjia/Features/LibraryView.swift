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
    private var replaceOnNextPage = false

    var creators: [Creator] = []
    private var search = ""
    private var sourceId: String?
    private var options = FeedOptions()

    func reload(client: APIClient, filter: LibraryFilter, search: String = "", sourceId: String? = nil, options: FeedOptions = FeedOptions(), onError: (Error) -> Void) async {
        generation += 1
        cursor = nil
        exhausted = false
        // Show this filter's last first page until the fresh one arrives.
        self.sourceId = sourceId
        self.options = options
        if search.isEmpty, let saved = client.cachedFeed(filter: filter, sourceId: sourceId, options: options) {
            items = saved.items
        } else if !search.isEmpty {
            items = []
        }
        replaceOnNextPage = true
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
            let page = try await client.feed(filter: filter, cursor: cursor, search: search, sourceId: sourceId, options: options)
            guard started == generation else { return }
            if replaceOnNextPage {
                items = page.items
                replaceOnNextPage = false
            } else {
                let known = Set(items.map(\.id))
                items.append(contentsOf: page.items.filter { !known.contains($0.id) })
            }
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
    @State private var sources: [LibrarySource] = []
    @State private var sourceId: String?
    @State private var options = FeedOptions()

    private var query: String { search.trimmingCharacters(in: .whitespacesAndNewlines) }

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 6), count: 3)

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    filterPicker
                    if query.isEmpty && !sources.isEmpty {
                        sourceChips
                    }
                    if !feed.creators.isEmpty {
                        creatorResults
                    }
                    // Stays up when a narrowing finds nothing, so it can be undone.
                    if !feed.items.isEmpty || options != FeedOptions() {
                        SectionHeader(title: "作品", count: query.isEmpty ? nil : "\(feed.items.count)\(feed.loading ? "+" : "")") {
                            optionsMenu
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
                                .buttonStyle(.glassProminent)
                                .tint(Theme.violet2)
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
            .scrollDismissesKeyboard(.immediately)
            .screenBackground()
            .navigationTitle("作品")
            .navigationBarTitleDisplayMode(.large)
            // Always shown under the title, as the old search row was.
            .searchable(text: $search, placement: .navigationBarDrawer(displayMode: .automatic), prompt: "作品描述、博主名或抖音号")
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .refreshable { await reload() }
            .navigationDestination(for: CreatorRoute.self) { CreatorArchiveView(creatorId: $0.id) }
            .task {
                if sources.isEmpty { sources = (model.client.cachedLibrarySources() ?? []).filter(\.browsable) }
                if let fresh = try? await model.client.librarySources() { sources = fresh.filter(\.browsable) }
            }
            .task(id: "\(filter.rawValue)|\(query)|\(sourceId ?? "")|\(options.hashValue)") {
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

    /// What the standard order means here: the list's own order, or when it was starred / collected.
    private var standardSortTitle: String {
        if sourceId != nil && query.isEmpty { return "收藏顺序" }
        return filter == .starred ? "精选时间" : "最近收藏"
    }

    private func sortTitle(_ sort: FeedOptions.Sort) -> String {
        switch sort {
        case .standard: standardSortTitle
        case .published: "最新发布"
        case .random: "随机"
        }
    }

    private var optionsMenu: some View {
        Menu {
            Picker("排序", selection: Binding(get: { options.sort }, set: { sort in
                options.sort = sort
                if sort == .random { options.seed = Int.random(in: 1...999_999) }
            })) {
                ForEach(FeedOptions.Sort.allCases, id: \.self) { Text(sortTitle($0)).tag($0) }
            }
            if options.sort == .random {
                Button("换一批", systemImage: "shuffle") { options.seed = Int.random(in: 1...999_999) }
            }
            Section("类型") {
                Picker("类型", selection: $options.kind) {
                    ForEach(FeedOptions.Kind.allCases, id: \.self) { Text($0.title).tag($0) }
                }
            }
            if options.kind != .gallery {
                Section("时长") {
                    Picker("时长", selection: $options.length) {
                        ForEach(FeedOptions.Length.allCases, id: \.self) { Text($0.title).tag($0) }
                    }
                }
            }
            Section("收藏时间") {
                Picker("收藏时间", selection: $options.period) {
                    ForEach(FeedOptions.Period.allCases, id: \.self) { Text($0.title).tag($0) }
                }
            }
            if options != FeedOptions() {
                Button("恢复默认", systemImage: "arrow.counterclockwise") { options = FeedOptions() }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: options.isNarrowed ? "line.3.horizontal.decrease.circle.fill" : "arrow.up.arrow.down")
                    .foregroundStyle(options.isNarrowed ? Theme.violet4 : Theme.muted)
                Text(optionsSummary)
                    .foregroundStyle(options == FeedOptions() ? Theme.muted : Theme.violet4)
            }
            .contentShape(Rectangle())
        }
        .accessibilityLabel("排序和筛选：\(optionsSummary)")
    }

    private var optionsSummary: String {
        var parts = [sortTitle(options.sort)]
        if options.kind != .all { parts.append(options.kind.title) }
        if options.kind != .gallery && options.length != .all { parts.append(options.length.title) }
        if options.period != .all { parts.append(options.period.title) }
        return parts.joined(separator: " · ")
    }

    private var filterPicker: some View {
        Picker("筛选", selection: $filter) {
            ForEach(LibraryFilter.allCases) { option in
                Text(option.title).tag(option)
            }
        }
        .pickerStyle(.segmented)
        .padding(.top, 4)
    }

    /// Likes, favourites, each folder…: one tap narrows the grid to that list.
    private var sourceChips: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 6) {
                chip(title: "全部来源", systemImage: "square.grid.2x2", count: nil, selected: sourceId == nil) {
                    sourceId = nil
                }
                ForEach(sources) { source in
                    chip(title: source.title, systemImage: source.systemImage, count: source.discoveredCount,
                         selected: sourceId == source.id) {
                        sourceId = sourceId == source.id ? nil : source.id
                    }
                }
            }
        }
        .scrollIndicators(.hidden)
        // Run edge to edge so the row reads as scrollable instead of cut off.
        .contentMargins(.horizontal, Theme.pageInset, for: .scrollContent)
        .padding(.horizontal, -Theme.pageInset)
    }

    private func chip(title: String, systemImage: String, count: Int?, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: systemImage).font(.system(size: 11, weight: .semibold))
                Text(title).font(.system(size: 12.5, weight: .semibold)).lineLimit(1)
                if let count {
                    Text(Format.integer(count)).font(.system(size: 11)).monospacedDigit()
                        .foregroundStyle(selected ? Theme.text.opacity(0.8) : Theme.muted)
                }
            }
            .foregroundStyle(selected ? Theme.text : Theme.muted)
            .padding(.horizontal, 11)
            .padding(.vertical, 7)
            .background(selected ? Theme.violet2.opacity(0.35) : Color.white.opacity(0.06), in: Capsule())
            .overlay(Capsule().strokeBorder(selected ? Theme.violet3.opacity(0.7) : Color.white.opacity(0.08), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private static var initialFilter: LibraryFilter {
        #if DEBUG
        return UserDefaults.standard.string(forKey: "devFilter").flatMap(LibraryFilter.init(rawValue:)) ?? .all
        #else
        return .all
        #endif
    }

    private var emptyTitle: String {
        if options.isNarrowed { return "没有符合筛选的作品" }
        return switch filter {
        case .all: "还没有收藏"
        case .saved: "还没有存到 NAS 的作品"
        case .starred: "还没有精选，在播放时点星标加入"
        }
    }

    private func reload() async {
        await feed.reload(client: model.client, filter: filter, search: query, sourceId: query.isEmpty ? sourceId : nil, options: options, onError: model.handle)
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
