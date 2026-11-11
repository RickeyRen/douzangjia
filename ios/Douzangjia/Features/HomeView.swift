import SwiftUI

struct VanishedListRoute: Hashable {}

struct HomeView: View {
    @Environment(AppModel.self) private var model
    @State private var home: HomeSnapshot?
    @State private var missing: MissingSummary?
    @State private var poller = ProgressPoller()
    @State private var loadError: String?
    @State private var live = false
    @State private var confirmSaveAll = false
    @State private var queueing = false
    @State private var saveAllNotice: String?
    @State private var showSettings = false
    @State private var player: PlayerSelection?

    @Environment(\.selectTab) private var selectTab

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if let loadError, home == nil {
                        ContentUnavailableView {
                            Label("读取失败", systemImage: "wifi.exclamationmark")
                        } description: {
                            Text(loadError)
                        } actions: {
                            Button("重试") { Task { await load() } }
                                .buttonStyle(.glassProminent)
                                .tint(Theme.violet2)
                        }
                        .card()
                    }
                    hero
                    kpis
                    downloadSection
                    if let vanished = home?.vanishedCreators, !vanished.isEmpty {
                        vanishedShelf(vanished, total: home?.stats.vanishedCreators ?? vanished.count)
                    }
                    if let home, !home.recent.isEmpty {
                        shelf("最近收藏", items: home.recent)
                    }
                    if let home, !home.starred.isEmpty {
                        shelf("精选", items: home.starred)
                    }
                }
                .padding(.horizontal, Theme.pageInset)
                .padding(.bottom, 12)
            }
            .scrollIndicators(.hidden)
            .screenBackground()
            .navigationTitle("抖藏家")
            .toolbar { toolbarContent }
            .refreshable { await load() }
            .task { await load() }
            .onAppear { poller.start(client: model.client, onError: model.handle) }
            .onDisappear { poller.stop() }
            .navigationDestination(for: CreatorRoute.self) { CreatorArchiveView(creatorId: $0.id) }
            .navigationDestination(for: VanishedListRoute.self) { _ in VanishedCreatorsView() }
            .sheet(isPresented: $showSettings) { SettingsView() }
            .fullScreenCover(item: $player) { selection in
                PlayerView(items: selection.items, startIndex: selection.index)
            }
            .alert(saveAllNotice ?? "", isPresented: Binding(
                get: { saveAllNotice != nil },
                set: { if !$0 { saveAllNotice = nil } }
            )) {
                Button("好") {}
            }
            // An alert, not a confirmation dialog: on iOS 26 a dialog attached to the
            // whole stack pops up as a bubble at the top of the screen, far from the button.
            .alert(
                "把 \(Format.integer(missing?.unqueued ?? 0)) 个收藏作品全部存到 NAS？",
                isPresented: $confirmSaveAll
            ) {
                Button("取消", role: .cancel) {}
                Button("开始下载") { Task { await saveAll() } }
            } message: {
                if let bytes = missing?.estimatedBytes {
                    Text("按已下载作品的平均大小估算，大约需要 \(Format.bytes(bytes))。")
                }
            }
        }
    }

    // MARK: Sections

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            // Saved data can be on screen before (or without) the NAS answering.
            if loadError != nil {
                ConnectionPill(text: "NAS 离线", color: Theme.red)
            } else if live {
                ConnectionPill(text: "NAS 在线", color: Theme.lime)
            } else {
                ConnectionPill(text: "连接中", color: Theme.muted)
            }
        }
        ToolbarSpacer(.fixed, placement: .topBarTrailing)
        ToolbarItem(placement: .topBarTrailing) {
            Button("设置", systemImage: "gearshape") { showSettings = true }
        }
    }

    private var hero: some View {
        let stats = home?.stats
        let videoShare = stats.map { $0.items > 0 ? Double($0.videos) / Double($0.items) : 0 } ?? 0
        return VStack(alignment: .leading, spacing: 4) {
            Text("收藏作品").font(.system(size: 13)).foregroundStyle(Theme.muted)
            HStack(alignment: .bottom) {
                if let stats {
                    Text(Format.integer(stats.items))
                        .font(Theme.number(36))
                        .foregroundStyle(Theme.text)
                        .lineLimit(1).minimumScaleFactor(0.6)
                } else {
                    placeholder(width: 120, height: 38)
                }
                Spacer(minLength: 8)
                VStack(alignment: .leading, spacing: 3) {
                    legend(color: Theme.violet, label: "视频", value: stats?.videos)
                    legend(color: Theme.violet4, label: "图集", value: stats?.galleries)
                }
                .padding(.bottom, 4)
            }
            GeometryReader { proxy in
                HStack(spacing: 3) {
                    Capsule().fill(Theme.violet).frame(width: max(6, (proxy.size.width - 3) * videoShare))
                    Capsule().fill(Theme.violet4)
                }
            }
            .frame(height: 6)
            .opacity(stats == nil ? 0.3 : 1)
            .padding(.top, 6)
        }
        .card()
    }

    private func legend(color: Color, label: String, value: Int?) -> some View {
        HStack(spacing: 6) {
            RoundedRectangle(cornerRadius: 2.5).fill(color).frame(width: 8, height: 8)
            Text(label).foregroundStyle(Theme.muted)
            Text(value.map { Format.integer($0) } ?? "—").foregroundStyle(Theme.text).monospacedDigit()
        }
        .font(.system(size: 11.5, weight: .medium))
        .lineLimit(1)
    }

    private var kpis: some View {
        let stats = home?.stats
        return HStack(spacing: 8) {
            KPITile(title: "已存到 NAS", value: stats.map { Format.integer($0.downloadedItems) },
                    detail: stats.map { "占用 \(Format.bytes($0.archivedBytes))" })
            KPITile(title: "博主", value: stats.map { Format.integer($0.creators) }, detail: "收藏涉及")
            if let vanished = stats?.vanishedCreators {
                KPITile(title: "已在抖音消失", value: Format.integer(vanished), unit: "位",
                        detail: stats.map { "\(Format.integer($0.gone)) 个作品没了" },
                        detailColor: (stats?.gone ?? 0) > 0 ? Theme.redText : Theme.muted)
            } else {
                KPITile(title: "已在抖音消失", value: stats.map { Format.integer($0.gone) }, unit: "个",
                        detail: "删除或私密", detailColor: (stats?.gone ?? 0) > 0 ? Theme.redText : Theme.muted)
            }
        }
    }

    @ViewBuilder
    private var downloadSection: some View {
        if let progress = poller.progress {
            let hasAny = progress.active != nil || progress.failedTotal > 0 || (missing?.unqueued ?? 0) > 0
            if hasAny {
                SectionHeader(title: "下载") {
                    Button { selectTab(2) } label: {
                        HStack(spacing: 2) { Text("全部"); Image(systemName: "chevron.right").font(.system(size: 9, weight: .semibold)) }
                    }
                    .buttonStyle(.plain)
                }
            }
            if let active = progress.active {
                DownloadProgressCard(active: active, compact: true) { await poller.refresh(client: model.client) }
            }
            // Progress, failures and "save everything" are shown together so none hides another.
            if progress.failedTotal > 0 {
                FailureSection(progress: progress, compact: true) { await poller.refresh(client: model.client) }
            }
            if let missing, missing.unqueued > 0 {
                saveAllBanner(missing)
            }
        }
    }

    private func saveAllBanner(_ missing: MissingSummary) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            (Text("还有 ") + Text(Format.integer(missing.unqueued)).foregroundColor(Theme.lime).monospacedDigit()
             + Text(" 个收藏作品没有存到 NAS"))
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
            HStack(alignment: .center, spacing: 10) {
                Text(missing.estimatedBytes.map { "约 \(Format.bytes($0))" } ?? "目前只有抖音上的链接，作者删除后就看不到了")
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.text.opacity(0.78))
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Button {
                    confirmSaveAll = true
                } label: {
                    HStack(spacing: 6) {
                        if queueing { ProgressView().controlSize(.small).tint(Color(hex: 0x120C33)) }
                        Text("全部存到 NAS").fontWeight(.semibold)
                        Image(systemName: "arrow.up.right").font(.system(size: 11, weight: .bold))
                    }
                    .foregroundStyle(Color(hex: 0x120C33))
                }
                // Lavender fill: a violet one would vanish into the violet card.
                .buttonStyle(.glassProminent)
                .tint(Theme.text)
                .disabled(queueing)
            }
        }
        .padding(EdgeInsets(top: 14, leading: 16, bottom: 14, trailing: 14))
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.actionGradient)
        .overlay(alignment: .bottomTrailing) {
            Circle().strokeBorder(.white.opacity(0.12), lineWidth: 1).frame(width: 160, height: 160).offset(x: 40, y: 70)
                .allowsHitTesting(false)
        }
        .clipShape(RoundedRectangle(cornerRadius: Theme.radiusCard, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.radiusCard, style: .continuous).strokeBorder(Theme.violet4.opacity(0.25), lineWidth: 1))
    }

    private func vanishedShelf(_ creators: [VanishedCreatorTile], total: Int) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            NavigationLink(value: VanishedListRoute()) {
                SectionHeader(title: "已在抖音消失", count: "\(Format.integer(total)) 位") {
                    HStack(spacing: 2) { Text("全部"); Image(systemName: "chevron.right").font(.system(size: 9, weight: .semibold)) }
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(alignment: .top, spacing: 6) {
                    ForEach(creators) { creator in
                        NavigationLink(value: CreatorRoute(id: creator.id)) {
                            VStack(spacing: 5) {
                                CreatorAvatar(path: creator.avatarUrl, size: 48)
                                    .saturation(0.35).brightness(-0.08)
                                Text(creator.nickname)
                                    .font(.system(size: 11.5, weight: .semibold))
                                    .foregroundStyle(Theme.text)
                                    .lineLimit(1)
                                if let status = CreatorArchiveStatus(rawValue: creator.status) {
                                    StatusBadge(status: status)
                                }
                            }
                            .frame(width: 66)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .scrollClipDisabled()
        }
    }

    private func shelf(_ title: String, items: [FeedItem]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: title, count: "\(items.count)")
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(alignment: .top, spacing: 10) {
                    ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
                        Button {
                            player = PlayerSelection(items: items, index: index)
                        } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                MediaTile(item: item, showTitle: false, radius: 16)
                                    .frame(width: 112, height: 150)
                                Text(item.title)
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundStyle(Theme.text)
                                    .lineLimit(2)
                                    .frame(height: 32, alignment: .topLeading)
                                Text("@\(item.author)")
                                    .font(.system(size: 11))
                                    .foregroundStyle(Theme.muted)
                                    .lineLimit(1)
                            }
                            .frame(width: 112, alignment: .leading)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .scrollClipDisabled()
        }
    }

    private func placeholder(width: CGFloat, height: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: 6).fill(Theme.panel3).frame(width: width, height: height)
    }

    // MARK: Actions

    private func load() async {
        // Show the last answer at once; the fresh one replaces it when it lands.
        if home == nil { home = model.client.cachedHome() }
        if missing == nil { missing = model.client.cachedMissingSummary() }
        do {
            async let snapshot = model.client.home()
            async let summary = model.client.missingSummary()
            home = try await snapshot
            missing = try? await summary
            loadError = nil
            live = true
        } catch is CancellationError {
            return
        } catch {
            model.handle(error)
            loadError = error.localizedDescription
        }
        await poller.refresh(client: model.client)
    }

    private func saveAll() async {
        queueing = true
        defer { queueing = false }
        do {
            let result = try await model.client.archiveMissing()
            await poller.refresh(client: model.client)
            missing = try? await model.client.missingSummary()
            if result.queueing == true {
                saveAllNotice = "正在把作品加入下载队列，作品多时要几分钟，进度会出现在首页上方。"
            } else if result.batch.totalItems == 0, result.skipped > 0 {
                saveAllNotice = "这 \(Format.integer(result.skipped)) 个作品还缺少下载信息，等下次同步补上后再试。"
            } else {
                saveAllNotice = "已加入下载队列，进度会出现在首页上方。"
            }
        } catch {
            model.handle(error)
            saveAllNotice = error.localizedDescription
        }
    }
}

struct PlayerSelection: Identifiable {
    let id = UUID()
    let items: [FeedItem]
    let index: Int
}

private struct KPITile: View {
    let title: String
    let value: String?
    var unit: String?
    let detail: String?
    var detailColor: Color = Theme.muted

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.system(size: 11)).foregroundStyle(Theme.muted).lineLimit(1).minimumScaleFactor(0.85)
            if let value {
                HStack(alignment: .firstTextBaseline, spacing: 2) {
                    Text(value).font(Theme.number(22)).foregroundStyle(Theme.text)
                    if let unit { Text(unit).font(.system(size: 12)).foregroundStyle(Theme.muted) }
                }
                .lineLimit(1).minimumScaleFactor(0.6)
            } else {
                RoundedRectangle(cornerRadius: 6).fill(Theme.panel3).frame(width: 56, height: 24)
            }
            Text(detail ?? " ").font(.system(size: 10.5)).foregroundStyle(detailColor).lineLimit(1).minimumScaleFactor(0.8)
        }
        .card(radius: Theme.radiusInner, padding: EdgeInsets(top: 10, leading: 12, bottom: 10, trailing: 10))
    }
}

/// Cover thumbnail with the design's status badge (已存 / 仅封面), duration and optional title.
struct MediaTile: View {
    let item: FeedItem
    var showTitle = true
    var radius: CGFloat = Theme.radiusTile

    private var coverOnly: Bool { item.videoIsLost || item.videoIsAtRisk }

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .bottomLeading) {
                RemoteImage(path: item.previewPath)
                    .frame(width: proxy.size.width, height: proxy.size.height)
                    .clipped()
                    .saturation(item.videoIsLost ? 0.25 : 1)
                    .brightness(item.videoIsLost ? -0.18 : 0)
                LinearGradient(colors: [.clear, .black.opacity(showTitle ? 0.7 : 0.5)], startPoint: .center, endPoint: .bottom)
                if showTitle {
                    Text(item.title)
                        .font(.system(size: 11, weight: .semibold))
                        .lineLimit(2)
                        .foregroundStyle(.white)
                        .shadow(color: .black.opacity(0.6), radius: 3, y: 1)
                        .padding(.horizontal, 8)
                        .padding(.bottom, 24)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .overlay(alignment: .topLeading) { badge.padding(6) }
            .overlay(alignment: .topTrailing) {
                if item.starred == true {
                    Image(systemName: "star.fill")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(Theme.lime)
                        .frame(width: 19, height: 19)
                        .background(.black.opacity(0.45), in: Circle())
                        .padding(6)
                }
            }
            .overlay(alignment: .bottomTrailing) {
                if item.isGallery {
                    cornerLabel(Image(systemName: "square.on.square").font(.system(size: 9.5, weight: .semibold)))
                } else if let duration = Format.duration(item.douyin?.durationMs) {
                    cornerLabel(Text(duration).font(.system(size: 10.5, weight: .semibold)).monospacedDigit())
                }
            }
        }
        .background(Theme.panel2)
        .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
        .contentShape(Rectangle())
    }

    private func cornerLabel(_ content: some View) -> some View {
        content
            .foregroundStyle(.white)
            .padding(.horizontal, 6).padding(.vertical, 1.5)
            .background(.black.opacity(0.45), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
            .padding(6)
    }

    @ViewBuilder
    private var badge: some View {
        if item.isSaved {
            HStack(spacing: 3) {
                Image(systemName: "checkmark").font(.system(size: 8, weight: .heavy))
                Text("已存")
            }
            .modifier(TileBadge(fill: Theme.violet.opacity(0.92), foreground: .white, glow: true))
        } else if coverOnly {
            Text("仅封面").modifier(TileBadge(fill: Color(hex: 0x0A090E, opacity: 0.72), foreground: Color(hex: 0xC9C5D8)))
        } else {
            HStack(spacing: 3) {
                Image(systemName: item.local?.state == "downloading" ? "arrow.down" : "icloud").font(.system(size: 8, weight: .bold))
                Text(item.local?.state == "downloading" ? "下载中" : "未存")
            }
            .modifier(TileBadge(fill: Color(hex: 0x0A090E, opacity: 0.72), foreground: Color(hex: 0xC9C5D8)))
        }
    }
}

private struct TileBadge: ViewModifier {
    let fill: Color
    let foreground: Color
    var glow = false

    func body(content: Content) -> some View {
        content
            .font(.system(size: 10.5, weight: .semibold))
            .lineLimit(1)
            .fixedSize()
            .foregroundStyle(foreground)
            .padding(.horizontal, 7)
            .frame(height: 19)
            .background(fill, in: Capsule())
            .overlay(Capsule().strokeBorder(glow ? .clear : Theme.text.opacity(0.18), lineWidth: 1))
            .shadow(color: glow ? Theme.violet.opacity(0.5) : .clear, radius: 4, y: 2)
    }
}
