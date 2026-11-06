import SwiftUI

/// Pushes a creator's archive page; registered once at the root of the home stack.
struct CreatorRoute: Hashable {
    let id: String
}

/// Creators Douyin banned, reset, closed or emptied, shown as they were.
struct VanishedCreatorsView: View {
    @Environment(AppModel.self) private var model
    @State private var creators: [Creator]?
    @State private var counts: [String: Int] = [:]
    @State private var cursor: String?
    @State private var error: String?
    @State private var loadingMore = false

    var body: some View {
        List {
            Section {
                Text("被封号、资料被重置或注销的博主。这里保留着他们原来的名字、头像和你存下的作品。")
                    .font(.footnote).foregroundStyle(.secondary)
                    .listRowBackground(Color.clear)
            }
            if let creators {
                if creators.isEmpty {
                    ContentUnavailableView(
                        "还没有发现消失的博主",
                        systemImage: "person.crop.circle.badge.questionmark",
                        description: Text("后台会慢慢检查你收藏过的博主，一旦有人被封号或资料被重置，就会出现在这里。")
                    )
                    .listRowBackground(Color.clear)
                }
                ForEach(creators) { creator in
                    NavigationLink(value: CreatorRoute(id: creator.id)) {
                        VanishedCreatorRow(creator: creator)
                    }
                    .onAppear {
                        if creator.id == creators.last?.id { Task { await loadMore() } }
                    }
                }
                if loadingMore { ProgressView().frame(maxWidth: .infinity) }
            } else if let error {
                ContentUnavailableView {
                    Label("读取失败", systemImage: "wifi.exclamationmark")
                } description: {
                    Text(error)
                } actions: {
                    Button("重试") { Task { await load() } }
                }
            } else {
                ProgressView().frame(maxWidth: .infinity).listRowBackground(Color.clear)
            }
        }
        .navigationTitle("消失的博主")
        .refreshable { await load() }
        .task { if creators == nil { await load() } }
    }

    private func load() async {
        do {
            let page = try await model.client.vanishedCreators(cursor: nil)
            creators = page.items
            counts = page.counts
            cursor = page.nextCursor
            error = nil
        } catch {
            model.handle(error)
            self.error = (error as? APIError)?.message ?? error.localizedDescription
        }
    }

    private func loadMore() async {
        guard let cursor, !loadingMore else { return }
        loadingMore = true
        defer { loadingMore = false }
        if let page = try? await model.client.vanishedCreators(cursor: cursor) {
            creators = (creators ?? []) + page.items
            self.cursor = page.nextCursor
        }
    }
}

private struct VanishedCreatorRow: View {
    let creator: Creator

    var body: some View {
        HStack(spacing: 12) {
            CreatorAvatar(path: creator.avatarUrl, size: 52).grayscale(0.85)
            VStack(alignment: .leading, spacing: 3) {
                Text(creator.nickname).font(.headline).lineLimit(1)
                if let current = creator.archive?.currentNickname, current != creator.nickname {
                    Text("现在显示为 \(current)").font(.caption).foregroundStyle(.secondary).strikethrough().lineLimit(1)
                }
                HStack(spacing: 6) {
                    if let status = creator.archive?.status { StatusBadge(status: status) }
                    Text("\(Format.integer(creator.knownItemCount)) 个作品 · 已存 \(Format.integer(creator.archivedItemCount))")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 2)
    }
}

struct StatusBadge: View {
    let status: CreatorArchiveStatus

    var body: some View {
        Text(status.label)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 7).padding(.vertical, 2)
            .foregroundStyle(tint)
            .background(tint.opacity(0.15), in: Capsule())
    }

    private var tint: Color {
        switch status {
        case .reset: .orange
        case .banned: .red
        default: .secondary
        }
    }
}

struct CreatorAvatar: View {
    let path: String?
    let size: CGFloat

    var body: some View {
        Group {
            if path != nil {
                RemoteImage(path: path, failureIcon: "person.fill")
            } else {
                Image(systemName: "person.fill")
                    .font(.system(size: size * 0.45))
                    .foregroundStyle(.tertiary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color(.tertiarySystemFill))
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .overlay(Circle().strokeBorder(Color(.separator), lineWidth: 0.5))
    }
}

/// A removed creator's profile, laid out like their Douyin homepage used to be.
struct CreatorArchiveView: View {
    @Environment(AppModel.self) private var model
    let creatorId: String
    @State private var creator: Creator?
    @State private var feed = CreatorFeed()
    @State private var player: PlayerSelection?
    @State private var busy = false
    @State private var message: String?

    private let columns = [GridItem(.adaptive(minimum: 110), spacing: 3)]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if let creator { header(creator) } else { ProgressView().frame(maxWidth: .infinity).padding(40) }
                LazyVGrid(columns: columns, spacing: 3) {
                    ForEach(Array(feed.items.enumerated()), id: \.element.id) { index, item in
                        Button {
                            player = PlayerSelection(items: feed.items, index: index)
                        } label: {
                            MediaTile(item: item).aspectRatio(3 / 4, contentMode: .fit)
                        }
                        .buttonStyle(.plain)
                        .onAppear {
                            if index >= feed.items.count - 9 {
                                Task { await feed.loadMore(client: model.client, creatorId: creatorId, onError: model.handle) }
                            }
                        }
                    }
                }
                .padding(.horizontal, 3)
                .padding(.top, 12)
                if feed.loading { ProgressView().frame(maxWidth: .infinity).padding(24) }
            }
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle(creator?.nickname ?? "")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            if creator == nil { await load() }
        }
        .refreshable { await load() }
        .fullScreenCover(item: $player) { selection in
            PlayerView(items: selection.items, startIndex: selection.index) { feed.update($0) }
        }
    }

    private func header(_ creator: Creator) -> some View {
        let kept = creator.archive?.preserved
        let status = creator.archive?.status ?? .vanished
        return VStack(alignment: .leading, spacing: 12) {
            ZStack(alignment: .topTrailing) {
                Group {
                    if let cover = kept?.coverUrl {
                        RemoteImage(path: cover)
                    } else {
                        LinearGradient(colors: [Color(.systemGray4), Color(.systemGray6)], startPoint: .topLeading, endPoint: .bottomTrailing)
                    }
                }
                .frame(height: 130)
                .frame(maxWidth: .infinity)
                .clipped()
                .overlay(LinearGradient(colors: [.clear, Color(.systemGroupedBackground)], startPoint: .center, endPoint: .bottom))
                StatusBadge(status: status)
                    .padding(6)
                    .background(.ultraThinMaterial, in: Capsule())
                    .padding(10)
            }
            HStack(alignment: .bottom, spacing: 14) {
                CreatorAvatar(path: creator.avatarUrl, size: 84)
                    .overlay(Circle().strokeBorder(Color(.systemGroupedBackground), lineWidth: 3))
                VStack(alignment: .leading, spacing: 3) {
                    Text(creator.nickname).font(.title2.bold()).lineLimit(2)
                    Text([creator.uniqueId.map { "抖音号 \($0)" }, (kept?.ipLocation ?? creator.ipLocation).map { "IP 属地 \($0)" }]
                        .compactMap { $0 }.joined(separator: " · "))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, -48)
            if let signature = kept?.signature ?? creator.signature, !signature.isEmpty {
                Text(signature).font(.subheadline).padding(.horizontal, 16)
            }
            HStack(spacing: 18) {
                stat("关注", kept?.followingCount ?? creator.followingCount)
                stat("粉丝", kept?.followerCount ?? creator.followerCount)
                stat("获赞", kept?.totalFavorited ?? creator.totalFavorited)
                stat("作品", kept?.postCount ?? creator.postCount)
            }
            .padding(.horizontal, 16)
            note(creator, status: status, kept: kept)
            history(creator)
        }
    }

    @ViewBuilder
    private func stat(_ label: String, _ value: Int?) -> some View {
        if let value, value > 0 {
            HStack(spacing: 3) {
                Text(Format.compact(value)).font(.subheadline.bold()).monospacedDigit()
                Text(label).font(.subheadline).foregroundStyle(.secondary)
            }
        }
    }

    private func note(_ creator: Creator, status: CreatorArchiveStatus, kept: CreatorSnapshot?) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Group {
                Text(status.hint)
                Text("这里显示的是 Ta 原来的资料，最后一次见到是 \(Format.date(kept?.lastSeenAt ?? creator.lastSeenAt))。现在抖音上显示为「\(creator.archive?.currentNickname ?? "")」。")
                Text("记录了 \(Format.integer(creator.knownItemCount)) 个作品，其中 \(Format.integer(creator.archivedItemCount)) 个的视频已存到 NAS，其余只有封面和文字。")
            }
            .foregroundStyle(.secondary)
            if let message { Text(message) }
            HStack {
                if status == .reset {
                    Button { Task { await rescue() } } label: { Label("抢救全部作品", systemImage: "icloud.and.arrow.down") }
                        .buttonStyle(.borderedProminent)
                }
                Button { Task { await recheck() } } label: { Text("重新检查") }
                    .buttonStyle(.bordered)
                if busy { ProgressView() }
            }
            .disabled(busy)
            .padding(.top, 4)
        }
        .font(.footnote)
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .padding(.horizontal, 16)
    }

    @ViewBuilder
    private func history(_ creator: Creator) -> some View {
        let entries = (creator.archive?.history ?? []).reversed()
        if entries.count > 1 {
            VStack(alignment: .leading, spacing: 8) {
                Text("资料变化").font(.headline).padding(.horizontal, 16)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(Array(entries)) { snapshot in
                            HStack(spacing: 8) {
                                CreatorAvatar(path: snapshot.avatarUrl, size: 28)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(snapshot.nickname).font(.caption.weight(.semibold))
                                        .strikethrough(snapshot.degraded)
                                        .foregroundStyle(snapshot.degraded ? .secondary : .primary)
                                        .lineLimit(1)
                                    Text(Format.date(snapshot.firstSeenAt)).font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                            .padding(8)
                            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        }
                    }
                    .padding(.horizontal, 16)
                }
            }
        }
    }

    private func load() async {
        do {
            creator = try await model.client.creator(creatorId)
        } catch {
            model.handle(error)
            message = (error as? APIError)?.message ?? "读取失败"
        }
        await feed.reload(client: model.client, creatorId: creatorId, onError: model.handle)
    }

    private func recheck() async {
        busy = true
        defer { busy = false }
        do {
            let next = try await model.client.recheckCreator(creatorId)
            message = next.archive?.status == .active ? "这位博主在抖音上又能看到了" : "已重新检查，状态没有变化"
            creator = next
        } catch {
            model.handle(error)
            message = "检查失败，请确认抖音登录状态"
        }
    }

    private func rescue() async {
        busy = true
        defer { busy = false }
        do {
            try await model.client.archiveCreator(creatorId)
            message = "已开始抢救这位博主的全部作品"
        } catch {
            model.handle(error)
            message = "抢救失败，作品可能已经无法访问"
        }
    }
}

@Observable
@MainActor
final class CreatorFeed {
    var items: [FeedItem] = []
    var loading = false
    private var cursor: String?
    private var exhausted = false

    func reload(client: APIClient, creatorId: String, onError: (Error) -> Void) async {
        cursor = nil
        exhausted = false
        items = []
        await loadMore(client: client, creatorId: creatorId, onError: onError)
    }

    func loadMore(client: APIClient, creatorId: String, onError: (Error) -> Void) async {
        guard !loading, !exhausted else { return }
        loading = true
        defer { loading = false }
        do {
            let page = try await client.creatorFeed(creatorId, cursor: cursor)
            let known = Set(items.map(\.id))
            items.append(contentsOf: page.items.filter { !known.contains($0.id) })
            cursor = page.nextCursor
            exhausted = page.nextCursor == nil
        } catch {
            onError(error)
        }
    }

    func update(_ item: FeedItem) {
        if let index = items.firstIndex(where: { $0.id == item.id }) { items[index] = item }
    }
}
