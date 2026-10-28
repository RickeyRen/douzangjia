import SwiftUI

struct HomeView: View {
    @Environment(AppModel.self) private var model
    @State private var home: HomeSnapshot?
    @State private var missing: MissingSummary?
    @State private var poller = ProgressPoller()
    @State private var loadError: String?
    @State private var confirmSaveAll = false
    @State private var queueing = false
    @State private var showSettings = false
    @State private var player: PlayerSelection?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let loadError, home == nil {
                        ContentUnavailableView {
                            Label("读取失败", systemImage: "wifi.exclamationmark")
                        } description: {
                            Text(loadError)
                        } actions: {
                            Button("重试") { Task { await load() } }
                        }
                    }
                    stats
                    downloadSection
                    if let home, !home.recent.isEmpty {
                        shelf("最近收藏", items: home.recent)
                    }
                    if let home, !home.starred.isEmpty {
                        shelf("精选", items: home.starred)
                    }
                }
                .padding(16)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("抖藏家")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showSettings = true } label: { Image(systemName: "gearshape") }
                        .accessibilityLabel("设置")
                }
            }
            .refreshable { await load() }
            .task { await load() }
            .onAppear { poller.start(client: model.client, onError: model.handle) }
            .onDisappear { poller.stop() }
            .sheet(isPresented: $showSettings) { SettingsView() }
            .fullScreenCover(item: $player) { selection in
                PlayerView(items: selection.items, startIndex: selection.index)
            }
            .confirmationDialog(
                "把 \(Format.integer(missing?.missing ?? 0)) 个收藏作品全部存到 NAS？",
                isPresented: $confirmSaveAll,
                titleVisibility: .visible
            ) {
                Button("开始下载") { Task { await saveAll() } }
            } message: {
                if let bytes = missing?.estimatedBytes {
                    Text("按已下载作品的平均大小估算，大约需要 \(Format.bytes(bytes))。")
                }
            }
        }
    }

    // MARK: Sections

    private var stats: some View {
        LazyVGrid(columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)], spacing: 12) {
            StatTile(title: "收藏作品", systemImage: "film.stack", value: home.map { Format.integer($0.stats.items) },
                     detail: home.map { "视频 \(Format.integer($0.stats.videos)) · 图集 \(Format.integer($0.stats.galleries))" })
            StatTile(title: "已存到 NAS", systemImage: "externaldrive.badge.checkmark", value: home.map { Format.integer($0.stats.downloadedItems) },
                     detail: home.map { "占用 \(Format.bytes($0.stats.archivedBytes))" })
            StatTile(title: "博主", systemImage: "person.2", value: home.map { Format.integer($0.stats.creators) }, detail: "收藏涉及的创作者")
            StatTile(title: "已在抖音消失", systemImage: "icloud.slash", value: home.map { Format.integer($0.stats.gone) }, detail: "作者删除或设为私密")
        }
    }

    @ViewBuilder
    private var downloadSection: some View {
        if let progress = poller.progress {
            if let active = progress.active {
                DownloadProgressCard(active: active, compact: true) { await poller.refresh(client: model.client) }
            } else if progress.failedTotal > 0 {
                FailureSection(progress: progress) { await poller.refresh(client: model.client) }
            } else if let missing, missing.missing > 0 {
                saveAllBanner(missing)
            }
        }
    }

    private func saveAllBanner(_ missing: MissingSummary) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("还有 \(Format.integer(missing.missing)) 个收藏作品没有存到 NAS")
                .font(.headline)
            Text(missing.estimatedBytes.map { "按已下载作品的平均大小估算，大约需要 \(Format.bytes($0))。" }
                 ?? "它们目前只有抖音上的链接，作者删除后就看不到了。")
                .font(.subheadline).foregroundStyle(.secondary)
            Button {
                confirmSaveAll = true
            } label: {
                HStack {
                    if queueing { ProgressView().tint(.white) }
                    Label("全部存到 NAS", systemImage: "icloud.and.arrow.down")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(queueing)
        }
        .padding(16)
        .background(Color.brand.opacity(0.1), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private func shelf(_ title: String, items: [FeedItem]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.title3.bold())
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(spacing: 10) {
                    ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
                        Button {
                            player = PlayerSelection(items: items, index: index)
                        } label: {
                            MediaTile(item: item)
                                .frame(width: 128, height: 192)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .scrollClipDisabled()
        }
    }

    // MARK: Actions

    private func load() async {
        do {
            async let snapshot = model.client.home()
            async let summary = model.client.missingSummary()
            home = try await snapshot
            missing = try? await summary
            loadError = nil
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
            try await model.client.archiveMissing()
            await poller.refresh(client: model.client)
            missing = try? await model.client.missingSummary()
        } catch {
            model.handle(error)
            loadError = error.localizedDescription
        }
    }
}

struct PlayerSelection: Identifiable {
    let id = UUID()
    let items: [FeedItem]
    let index: Int
}

private struct StatTile: View {
    let title: String
    let systemImage: String
    let value: String?
    let detail: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(title, systemImage: systemImage).font(.caption).foregroundStyle(.secondary)
            Group {
                if let value {
                    Text(value).font(.title2.bold()).monospacedDigit()
                } else {
                    RoundedRectangle(cornerRadius: 6).fill(Color(.tertiarySystemFill)).frame(width: 70, height: 26)
                }
            }
            Text(detail ?? " ").font(.caption2).foregroundStyle(.secondary).lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

struct MediaTile: View {
    let item: FeedItem

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .bottomLeading) {
                RemoteImage(path: item.previewPath)
                    .frame(width: proxy.size.width, height: proxy.size.height)
                    .clipped()
                LinearGradient(colors: [.clear, .black.opacity(0.65)], startPoint: .center, endPoint: .bottom)
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.title).font(.caption2.weight(.semibold)).lineLimit(2)
                    Text("@\(item.author)").font(.caption2).opacity(0.8).lineLimit(1)
                }
                .foregroundStyle(.white)
                .padding(6)
            }
            .overlay(alignment: .topTrailing) {
                HStack(spacing: 4) {
                    if item.starred == true { Image(systemName: "star.fill").foregroundStyle(.yellow) }
                    if item.isGallery { Image(systemName: "square.on.square") }
                    if !item.isSaved { Image(systemName: "icloud") }
                    if let duration = Format.duration(item.douyin?.durationMs), !item.isGallery {
                        Text(duration).monospacedDigit()
                    }
                }
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 6).padding(.vertical, 3)
                .background(.black.opacity(0.45), in: Capsule())
                .padding(5)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .contentShape(Rectangle())
    }
}
