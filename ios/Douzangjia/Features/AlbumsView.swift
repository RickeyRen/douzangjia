import SwiftUI

/// The owner's own albums: covers, counts, create / rename / delete.
struct AlbumsView: View {
    @Environment(AppModel.self) private var model
    @State private var albums: [Album] = []
    @State private var tags: [TagCount] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var naming: AlbumNaming?
    @State private var nameDraft = ""
    @State private var deleting: Album?

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 14), count: 2)

    var body: some View {
        NavigationStack {
            ScrollView {
              VStack(spacing: 0) {
                if albums.isEmpty {
                    emptyState
                } else {
                    LazyVGrid(columns: columns, spacing: 18) {
                        ForEach(albums) { album in
                            NavigationLink(value: album) {
                                AlbumCard(album: album)
                            }
                            .buttonStyle(.plain)
                            .contextMenu {
                                Button("重命名", systemImage: "pencil") { startNaming(.rename(album)) }
                                Button("删除相册", systemImage: "trash", role: .destructive) { deleting = album }
                            }
                        }
                    }
                    .padding(.horizontal, Theme.pageInset)
                    .padding(.top, 8)
                    .padding(.bottom, 24)
                }
                if !tags.isEmpty { tagSection }
              }
            }
            .scrollIndicators(.hidden)
            .screenBackground()
            .navigationTitle("相册")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button { startNaming(.create) } label: { Image(systemName: "plus") }
                        .accessibilityLabel("新建相册")
                }
            }
            .refreshable { await load() }
            .task { await load() }
            .navigationDestination(for: Album.self) { album in
                AlbumDetailView(album: album) { await load() }
            }
            .navigationDestination(for: TagRoute.self) { TagWorksView(tag: $0.tag) }
            .navigationDestination(for: CreatorRoute.self) { CreatorArchiveView(creatorId: $0.id) }
            .alert(naming?.title ?? "", isPresented: Binding(get: { naming != nil }, set: { if !$0 { naming = nil } })) {
                TextField("相册名", text: $nameDraft)
                Button("取消", role: .cancel) {}
                // Closing the alert clears `naming` before the task runs; capture it now.
                Button(naming?.confirm ?? "好") {
                    let mode = naming
                    Task { await commitName(mode) }
                }
            }
            .confirmationDialog(
                "删除相册“\(deleting?.name ?? "")”？",
                isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }),
                titleVisibility: .visible
            ) {
                Button("删除相册", role: .destructive) {
                    let album = deleting
                    Task { await deleteAlbum(album) }
                }
            } message: {
                Text("只删除这个相册，里面的作品和 NAS 上的文件都还在。")
            }
        }
    }

    @ViewBuilder
    private var emptyState: some View {
        if !loaded {
            ProgressView().frame(maxWidth: .infinity).padding(60)
        } else if let error {
            ContentUnavailableView {
                Label("读取失败", systemImage: "wifi.exclamationmark")
            } description: {
                Text(error)
            } actions: {
                Button("重试") { Task { await load() } }.buttonStyle(.glassProminent).tint(Theme.violet2)
            }
            .padding(.top, 60)
        } else {
            ContentUnavailableView {
                Label("还没有相册", systemImage: "rectangle.stack")
            } description: {
                Text("把喜欢的作品归到一起：在这里新建，或者看作品时点标签按钮加入。")
            } actions: {
                Button("新建相册") { startNaming(.create) }.buttonStyle(.glassProminent).tint(Theme.violet2)
            }
            .padding(.top, 60)
        }
    }

    /// The owner's own tags, most used first; each opens the works carrying it.
    private var tagSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text("我的标签").font(.system(size: 20, weight: .bold))
                Spacer()
                Text("\(tags.count) 个").font(.system(size: 13)).foregroundStyle(Theme.muted)
            }
            FlowLayout(spacing: 8) {
                ForEach(tags, id: \.tag) { entry in
                    NavigationLink(value: TagRoute(tag: entry.tag)) {
                        HStack(spacing: 6) {
                            Text("#\(entry.tag)").font(.system(size: 14, weight: .medium)).foregroundStyle(Theme.text)
                            Text("\(entry.itemCount)").font(.system(size: 12).monospacedDigit()).foregroundStyle(Theme.muted)
                        }
                        .padding(.horizontal, 12).frame(height: 34)
                        .background(Theme.panel2, in: Capsule())
                        .overlay(Capsule().strokeBorder(Theme.line2, lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("标签 \(entry.tag)，\(entry.itemCount) 个作品")
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, Theme.pageInset)
        .padding(.bottom, 32)
    }

    private func load() async {
        if albums.isEmpty, let cached = model.client.cachedAlbums() { albums = cached }
        if tags.isEmpty, let cached = model.client.cachedTags() { tags = cached }
        if let fresh = try? await model.client.tags() { tags = fresh }
        do {
            albums = try await model.client.albums()
            error = nil
        } catch is CancellationError {
        } catch {
            if albums.isEmpty { self.error = (error as? APIError)?.message ?? error.localizedDescription }
        }
        loaded = true
    }

    private func startNaming(_ mode: AlbumNaming) {
        if case .rename(let album) = mode { nameDraft = album.name } else { nameDraft = "" }
        naming = mode
    }

    private func commitName(_ mode: AlbumNaming?) async {
        let name = nameDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let mode, !name.isEmpty else { return }
        do {
            switch mode {
            case .create:
                albums.append(try await model.client.createAlbum(name))
            case .rename(let album):
                let renamed = try await model.client.renameAlbum(album.id, to: name)
                if let index = albums.firstIndex(where: { $0.id == album.id }) { albums[index] = renamed }
            }
        } catch {
            model.handle(error)
        }
    }

    private func deleteAlbum(_ album: Album?) async {
        guard let album else { return }
        do {
            try await model.client.deleteAlbum(album.id)
            albums.removeAll { $0.id == album.id }
        } catch {
            model.handle(error)
        }
    }
}

private enum AlbumNaming {
    case create
    case rename(Album)

    var title: String {
        switch self {
        case .create: "新建相册"
        case .rename: "重命名相册"
        }
    }

    var confirm: String {
        switch self {
        case .create: "新建"
        case .rename: "保存"
        }
    }
}

/// Up to four covers in a square mosaic, like Photos.
private struct AlbumCard: View {
    let album: Album

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Color.clear
                .aspectRatio(1, contentMode: .fit)
                .overlay { mosaic }
                .clipShape(RoundedRectangle(cornerRadius: Theme.radiusTile))
                .overlay(RoundedRectangle(cornerRadius: Theme.radiusTile).strokeBorder(Theme.line2, lineWidth: 1))
            VStack(alignment: .leading, spacing: 2) {
                Text(album.name).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.text).lineLimit(1)
                Text("\(album.itemCount) 个作品").font(.caption).foregroundStyle(Theme.muted)
            }
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var mosaic: some View {
        let covers = album.covers
        if covers.isEmpty {
            ZStack {
                Theme.panel2
                Image(systemName: "rectangle.stack").font(.largeTitle).foregroundStyle(Theme.dim)
            }
        } else if covers.count < 4 {
            RemoteImage(path: covers[0], contentMode: .fill)
        } else {
            Grid(horizontalSpacing: 2, verticalSpacing: 2) {
                GridRow { tile(covers[0]); tile(covers[1]) }
                GridRow { tile(covers[2]); tile(covers[3]) }
            }
            .background(Theme.panel)
        }
    }

    private func tile(_ path: String) -> some View {
        Color.clear
            .overlay { RemoteImage(path: path, contentMode: .fill) }
            .clipped()
    }
}

/// One album's items; long-press to take one out.
struct AlbumDetailView: View {
    @Environment(AppModel.self) private var model
    let album: Album
    let onChange: () async -> Void
    @State private var items: [FeedItem] = []
    @State private var cursor: String?
    @State private var exhausted = false
    @State private var loading = false
    @State private var player: PlayerSelection?

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 6), count: 3)

    var body: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
                    Button {
                        player = PlayerSelection(items: items, index: index)
                    } label: {
                        Color.clear
                            .aspectRatio(3 / 4, contentMode: .fit)
                            .overlay { MediaTile(item: item, showTitle: false) }
                    }
                    .buttonStyle(.plain)
                    .contextMenu {
                        Button("从相册移出", systemImage: "minus.circle", role: .destructive) {
                            Task { await remove(item) }
                        }
                    }
                    .onAppear { if index >= items.count - 9 { Task { await loadMore() } } }
                }
            }
            .padding(.horizontal, Theme.pageInset)
            if loading {
                ProgressView().frame(maxWidth: .infinity).padding(24)
            } else if items.isEmpty {
                ContentUnavailableView(
                    "相册是空的", systemImage: "rectangle.stack",
                    description: Text("看作品时点右侧的标签按钮，就能加进这个相册。")
                )
                .padding(.top, 60)
            }
        }
        .scrollIndicators(.hidden)
        .screenBackground()
        .navigationTitle(album.name)
        .navigationBarTitleDisplayMode(.large)
        .refreshable { await reload() }
        .task { if items.isEmpty { await reload() } }
        .fullScreenCover(item: $player, onDismiss: { Task { await onChange() } }) { selection in
            PlayerView(items: selection.items, startIndex: selection.index) { changed in
                // Taken out of this album from the player: drop it here too.
                if changed.albums?.contains(where: { $0.id == album.id }) == false {
                    items.removeAll { $0.id == changed.id }
                } else if let index = items.firstIndex(where: { $0.id == changed.id }) {
                    items[index] = changed
                }
            }
        }
    }

    private func reload() async {
        cursor = nil
        exhausted = false
        items = []
        await loadMore()
    }

    private func loadMore() async {
        guard !loading, !exhausted else { return }
        loading = true
        defer { loading = false }
        do {
            let page = try await model.client.albumFeed(album.id, cursor: cursor)
            let known = Set(items.map(\.id))
            items.append(contentsOf: page.items.filter { !known.contains($0.id) })
            cursor = page.nextCursor
            exhausted = page.nextCursor == nil
        } catch is CancellationError {
        } catch {
            model.handle(error)
        }
    }

    private func remove(_ item: FeedItem) async {
        let before = items
        items.removeAll { $0.id == item.id }
        do {
            try await model.client.setAlbum(album.id, contains: item.id, false)
            await onChange()
        } catch {
            items = before
            model.handle(error)
        }
    }
}
