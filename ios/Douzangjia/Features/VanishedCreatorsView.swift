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
    @State private var search = ""
    @State private var monitor: CreatorMonitor?
    @State private var sort = "recent"

    var body: some View {
        List {
            Section {
                Text("被封号、资料被重置或注销的博主。这里保留着他们原来的名字、头像和你存下的作品。")
                    .font(.footnote).foregroundStyle(Theme.muted)
                    .listRowBackground(Color.clear)
                if let monitor {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("已检查 \(Format.integer(monitor.checkedCreators)) / \(Format.integer(monitor.libraryCreators)) 位博主，已记录 \(Format.integer(monitor.cataloguedCreators)) 位博主的 \(Format.integer(monitor.catalogItems)) 个作品。")
                            .foregroundStyle(Theme.muted)
                        if monitor.consecutiveFailures >= 5 {
                            Text("最近 \(monitor.consecutiveFailures) 次检查都没有拿到抖音的回应，可能是抖音登录失效或被限制了。")
                                .foregroundStyle(Theme.amber)
                        }
                    }
                    .font(.caption)
                    .listRowBackground(Color.clear)
                }
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
                    .listRowBackground(Theme.panel)
                    .listRowSeparatorTint(Theme.line2)
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
        // Keeps the hairline panel rows of the archive pages on the near-black canvas.
        .scrollContentBackground(.hidden)
        .screenBackground()
        .navigationTitle("已在抖音消失")
        .searchable(text: $search, prompt: "曾用名或抖音号")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Picker("排序", selection: $sort) {
                        Text("最近发现").tag("recent")
                        Text("存下最多").tag("saved")
                    }
                } label: {
                    Image(systemName: "arrow.up.arrow.down")
                }
                .accessibilityLabel("排序")
            }
        }
        .refreshable { await load() }
        // Waits briefly so each keystroke does not query the NAS.
        .task(id: "\(search)|\(sort)") {
            if !search.isEmpty { try? await Task.sleep(for: .milliseconds(300)) }
            if !Task.isCancelled { await load() }
        }
    }

    private func load() async {
        if creators == nil, search.isEmpty, let saved = model.client.cachedVanished(sort: sort) {
            creators = saved.items
            counts = saved.counts
            monitor = saved.monitor
        }
        do {
            let page = try await model.client.vanishedCreators(cursor: nil, search: search, sort: sort)
            creators = page.items
            counts = page.counts
            monitor = page.monitor
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
        if let page = try? await model.client.vanishedCreators(cursor: cursor, search: search, sort: sort) {
            creators = (creators ?? []) + page.items
            self.cursor = page.nextCursor
        }
    }
}

private struct VanishedCreatorRow: View {
    let creator: Creator

    var body: some View {
        HStack(spacing: 12) {
            CreatorAvatar(path: creator.avatarUrl, size: 48).saturation(0.35).brightness(-0.08)
            VStack(alignment: .leading, spacing: 3) {
                Text(creator.nickname).font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1)
                if let current = creator.archive?.currentNickname, current != creator.nickname {
                    Text("现在显示为 \(current)").font(.caption).foregroundStyle(Theme.muted).strikethrough().lineLimit(1)
                }
                Text("留档 \(Format.integer(creator.knownItemCount)) 个作品 · 已存 \(Format.integer(creator.archivedItemCount))")
                    .font(.system(size: 11.5)).foregroundStyle(Theme.muted).lineLimit(1)
            }
            Spacer(minLength: 6)
            if let status = creator.archive?.status { StatusBadge(status: status) }
        }
        .padding(.vertical, 2)
    }
}

struct StatusBadge: View {
    let status: CreatorArchiveStatus
    var large = false

    var body: some View {
        HStack(spacing: 4) {
            if large, status == .banned { Image(systemName: "nosign").font(.system(size: 10, weight: .bold)) }
            Text(status.label)
        }
        .font(.system(size: large ? 12 : 10.5, weight: .medium))
        .lineLimit(1)
        .fixedSize()
        .padding(.horizontal, large ? 10 : 7).padding(.vertical, large ? 4 : 2)
        .foregroundStyle(colors.text)
        .background(colors.fill, in: Capsule())
    }

    /// Red is reserved for bans; resets are amber, emptied accounts olive, the rest gray.
    private var colors: (text: Color, fill: Color) {
        switch status {
        case .banned: (Theme.redText, Theme.red.opacity(0.14))
        case .reset: (Color(hex: 0xFFB36E), Theme.amber.opacity(0.13))
        case .vanished: (Color(hex: 0xC9D46A), Theme.olive.opacity(0.22))
        default: (Color(hex: 0xB3B0C4), Theme.muted.opacity(0.14))
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
                    .font(.system(size: size * 0.42))
                    .foregroundStyle(Theme.dim)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Theme.panel3)
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .overlay(Circle().strokeBorder(Theme.line2, lineWidth: 0.5))
    }
}

enum ArchiveSegment: Hashable { case all, saved, cover }

/// A removed creator's profile, laid out like their Douyin homepage used to be.
struct CreatorArchiveView: View {
    @Environment(AppModel.self) private var model
    let creatorId: String
    @State private var creator: Creator?
    @State private var feed = CreatorFeed()
    @State private var player: PlayerSelection?
    @State private var busy = false
    @State private var message: String?
    @State private var segment: ArchiveSegment = .all

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 6), count: 3)

    /// Filters what is already loaded; more pages load as the grid scrolls.
    private var shown: [FeedItem] {
        switch segment {
        case .all: feed.items
        case .saved: feed.items.filter(\.isSaved)
        case .cover: feed.items.filter { !$0.isSaved }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if let creator { header(creator) } else { ProgressView().frame(maxWidth: .infinity).padding(40) }
                LazyVGrid(columns: columns, spacing: 6) {
                    let items = shown
                    ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
                        Button {
                            player = PlayerSelection(items: items, index: index)
                        } label: {
                            Color.clear
                                .aspectRatio(3 / 4, contentMode: .fit)
                                .overlay { MediaTile(item: item, showTitle: false) }
                        }
                        .buttonStyle(.plain)
                        .onAppear {
                            if index >= items.count - 9 {
                                Task { await feed.loadMore(client: model.client, creatorId: creatorId, onError: model.handle) }
                            }
                        }
                    }
                }
                .padding(.horizontal, Theme.pageInset)
                // A filtered segment can be short; keep paging while its end is on screen.
                Color.clear.frame(height: 1)
                    .task(id: "\(feed.items.count)|\(segment)") {
                        if segment != .all, creator != nil {
                            await feed.loadMore(client: model.client, creatorId: creatorId, onError: model.handle)
                        }
                    }
                if feed.loading { ProgressView().frame(maxWidth: .infinity).padding(24) }
            }
            .padding(.bottom, 12)
        }
        .scrollIndicators(.hidden)
        .screenBackground()
        .navigationTitle("博主存档")
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
        return VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 16) {
                ZStack(alignment: .bottomTrailing) {
                    CreatorAvatar(path: creator.avatarUrl, size: 76)
                        .saturation(0.35).brightness(-0.08)
                        .padding(3)
                        .overlay(Circle().strokeBorder((status == .banned ? Theme.red : Theme.gray).opacity(0.6), lineWidth: 1.5))
                    if status == .banned {
                        Image(systemName: "nosign")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(.white)
                            .frame(width: 24, height: 24)
                            .background(Theme.red, in: Circle())
                            .overlay(Circle().strokeBorder(Theme.bg, lineWidth: 3))
                            .offset(x: 2, y: 2)
                    }
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text(creator.nickname)
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundStyle(Theme.text)
                        .lineLimit(2)
                        .minimumScaleFactor(0.8)
                    let ids = [creator.uniqueId.map { "抖音号 \($0)" }, (kept?.ipLocation ?? creator.ipLocation).map { "IP 属地 \($0)" }]
                        .compactMap { $0 }.joined(separator: " · ")
                    if !ids.isEmpty {
                        Text(ids).font(.system(size: 12.5)).monospacedDigit().foregroundStyle(Theme.muted).lineLimit(2)
                    }
                    StatusBadge(status: status, large: true).padding(.top, 2)
                }
                Spacer(minLength: 0)
            }
            .padding(.top, 6)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(alignment: .top) {
                if let cover = kept?.coverUrl {
                    RemoteImage(path: cover)
                        .frame(height: 150)
                        .frame(maxWidth: .infinity)
                        .clipped()
                        .opacity(0.3)
                        .mask(LinearGradient(colors: [.black, .clear], startPoint: .top, endPoint: .bottom))
                        .padding(.horizontal, -Theme.pageInset)
                        .padding(.top, -60)
                        .allowsHitTesting(false)
                }
            }
            if let signature = kept?.signature ?? creator.signature, !signature.isEmpty {
                Text(signature).font(.system(size: 13)).foregroundStyle(Theme.text.opacity(0.85)).padding(.top, 4)
            }
            let extras = [("关注", kept?.followingCount ?? creator.followingCount),
                          ("获赞", kept?.totalFavorited ?? creator.totalFavorited),
                          ("抖音作品", kept?.postCount ?? creator.postCount)]
                .compactMap { label, value in value.flatMap { $0 > 0 ? "\(label) \(Format.compact($0))" : nil } }
            if !extras.isEmpty {
                Text(extras.joined(separator: " · ")).font(.system(size: 11.5)).monospacedDigit().foregroundStyle(Theme.muted)
            }
            // A creator still active on Douyin has nothing "original" to explain;
            // the note is only for profiles that changed or disappeared.
            if status != .active {
                note(creator, status: status, kept: kept)
            }
            HStack(spacing: 8) {
                ArchiveStat(title: "记录作品", value: Format.integer(creator.knownItemCount))
                ArchiveStat(title: "已存视频", value: Format.integer(creator.archivedItemCount), highlight: true)
                // Douyin reports 0 when the creator hides the count, so 0 reads as unknown.
                ArchiveStat(title: "粉丝", value: (kept?.followerCount ?? creator.followerCount).flatMap { $0 > 0 ? Format.compact($0) : nil } ?? "—")
            }
            saveBar(creator)
            history(creator)
            segmentPicker(creator)
        }
        .padding(.horizontal, Theme.pageInset)
    }

    private func note(_ creator: Creator, status: CreatorArchiveStatus, kept: CreatorSnapshot?) -> some View {
        HStack(alignment: .top, spacing: 10) {
            IconChip(systemImage: "clock.arrow.circlepath", size: 24, tint: Theme.violet4, fill: Theme.violet.opacity(0.25))
                .padding(.top, 1)
            VStack(alignment: .leading, spacing: 6) {
                if !status.hint.isEmpty {
                    Text(status.hint).foregroundStyle(Theme.text)
                }
                (Text("这里显示的是 Ta 原来的资料，最后一次见到是 \(Format.date(kept?.lastSeenAt ?? creator.lastSeenAt))。现在抖音上显示为「")
                 + Text(creator.archive?.currentNickname ?? "").foregroundColor(Theme.text).bold()
                 + Text("」。"))
                    .foregroundStyle(Color(hex: 0xCFCAE0))
                if let message { Text(message).foregroundStyle(Theme.violet4) }
                HStack(spacing: 8) {
                    if status == .reset {
                        Button { Task { await rescue() } } label: { Label("抢救全部作品", systemImage: "icloud.and.arrow.down") }
                            .buttonStyle(.glassProminent)
                            .tint(Theme.violet2)
                    }
                    Button { Task { await recheck() } } label: { Text("重新检查") }
                        .buttonStyle(.glass)
                    if busy { ProgressView().controlSize(.small) }
                }
                .controlSize(.small)
                .font(.system(size: 12.5, weight: .semibold))
                .disabled(busy)
                .padding(.top, 2)
            }
            .font(.system(size: 12.5))
            .lineSpacing(3)
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(EdgeInsets(top: 12, leading: 14, bottom: 12, trailing: 14))
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(colors: [Theme.violet.opacity(0.10), Theme.violet.opacity(0.04)], startPoint: .top, endPoint: .bottom),
            in: RoundedRectangle(cornerRadius: Theme.radiusInner, style: .continuous)
        )
        .background(Theme.panel, in: RoundedRectangle(cornerRadius: Theme.radiusInner, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.radiusInner, style: .continuous).strokeBorder(Theme.violet3.opacity(0.2), lineWidth: 1))
        .padding(.top, 8)
    }

    private func saveBar(_ creator: Creator) -> some View {
        let fraction = creator.knownItemCount > 0 ? Double(creator.archivedItemCount) / Double(creator.knownItemCount) : 0
        return VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(saveSummary(creator))
                    .font(.system(size: 12)).foregroundStyle(Theme.muted)
                    .lineLimit(2)
                Spacer(minLength: 8)
                Text("\(Int((fraction * 100).rounded()))%")
                    .font(.system(size: 13, weight: .semibold)).monospacedDigit()
                    .foregroundStyle(Theme.violet4)
            }
            GlowBar(fraction: fraction, height: 4)
        }
        .padding(.horizontal, 2)
        .padding(.top, 6)
    }

    private func segmentPicker(_ creator: Creator) -> some View {
        Picker("显示", selection: $segment) {
            Text("全部 \(Format.integer(creator.knownItemCount))").tag(ArchiveSegment.all)
            Text("已存 \(Format.integer(creator.archivedItemCount))").tag(ArchiveSegment.saved)
            Text("仅封面 \(Format.integer(max(0, creator.knownItemCount - creator.archivedItemCount)))").tag(ArchiveSegment.cover)
        }
        .pickerStyle(.segmented)
        .padding(.top, 8)
        .padding(.bottom, 6)
    }

    @ViewBuilder
    private func history(_ creator: Creator) -> some View {
        let entries = distinctProfiles((creator.archive?.history ?? []).reversed())
        if entries.count > 1 {
            VStack(alignment: .leading, spacing: 8) {
                SectionHeader(title: "资料变化", count: "\(entries.count)")
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(Array(entries)) { snapshot in
                            HStack(spacing: 8) {
                                CreatorAvatar(path: snapshot.avatarUrl, size: 28)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(snapshot.nickname).font(.system(size: 12, weight: .semibold))
                                        .strikethrough(snapshot.degraded)
                                        .foregroundStyle(snapshot.degraded ? Theme.muted : Theme.text)
                                        .lineLimit(1)
                                    Text(Format.date(snapshot.firstSeenAt)).font(.system(size: 10.5)).foregroundStyle(Theme.muted)
                                }
                            }
                            .padding(8)
                            .background(Theme.panel, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(Theme.line, lineWidth: 1))
                        }
                    }
                }
                .scrollClipDisabled()
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

private struct ArchiveStat: View {
    let title: String
    let value: String
    var highlight = false

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.system(size: 11)).foregroundStyle(Theme.muted).lineLimit(1)
            Text(value)
                .font(Theme.number(22))
                .foregroundStyle(highlight ? Theme.violet4 : Theme.text)
                .lineLimit(1).minimumScaleFactor(0.6)
        }
        .card(radius: Theme.radiusInner, padding: EdgeInsets(top: 10, leading: 12, bottom: 10, trailing: 10))
    }
}

/// Snapshots also record avatar or count changes; the strip shows only name changes.
private func distinctProfiles<S: Sequence>(_ snapshots: S) -> [CreatorSnapshot] where S.Element == CreatorSnapshot {
    var seen = Set<String>()
    return snapshots.filter { seen.insert($0.nickname).inserted }
}

/// One sentence for the save bar that stays true at 0%, partway and 100%.
private func saveSummary(_ creator: Creator) -> String {
    let saved = creator.archivedItemCount
    let known = creator.knownItemCount
    if known > 0 && saved >= known { return "全部 \(Format.integer(known)) 个作品都已存到 NAS" }
    if saved == 0 { return "还没有作品存到 NAS，只有封面和文字" }
    return "\(Format.integer(saved)) 个作品已存到 NAS，其余只有封面和文字"
}
