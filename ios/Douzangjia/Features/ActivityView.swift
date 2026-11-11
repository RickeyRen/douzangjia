import SwiftUI

struct ActivityView: View {
    @Environment(AppModel.self) private var model
    @State private var poller = ProgressPoller()
    @State private var health: SyncHealth?
    @State private var runs: [SyncRun]?
    @State private var syncing = false
    @State private var note: String?

    /// Only read for the storage summary in the header.
    @State private var stats: HomeStats?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    storage
                    downloads
                    SectionHeader(title: "同步")
                    syncPanel
                    history
                }
                .padding(.horizontal, Theme.pageInset)
                .padding(.bottom, 12)
            }
            .scrollIndicators(.hidden)
            .screenBackground()
            .navigationTitle("下载")
            .refreshable { await load() }
            .task { await load() }
            .onAppear { poller.start(client: model.client, onError: model.handle) }
            .onDisappear { poller.stop() }
        }
    }

    /// How much of the library is already on the NAS.
    @ViewBuilder
    private var storage: some View {
        if let stats {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Label("NAS 已存", systemImage: "externaldrive")
                        .labelStyle(.titleAndIcon)
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.muted)
                    Text(Format.bytes(stats.archivedBytes))
                        .font(.system(size: 12, weight: .semibold)).monospacedDigit()
                        .foregroundStyle(Theme.text)
                    Spacer(minLength: 8)
                    Text("\(Format.integer(stats.downloadedItems)) / \(Format.integer(stats.items)) 个作品")
                        .font(.system(size: 11.5)).monospacedDigit()
                        .foregroundStyle(Theme.muted)
                }
                .lineLimit(1)
                GlowBar(fraction: stats.items > 0 ? Double(stats.downloadedItems) / Double(stats.items) : 0, height: 5)
            }
            .card(padding: EdgeInsets(top: 12, leading: 16, bottom: 14, trailing: 16))
        }
    }

    @ViewBuilder
    private var downloads: some View {
        if let progress = poller.progress {
            if let active = progress.active {
                DownloadProgressCard(active: active) { await poller.refresh(client: model.client) }
            } else {
                HStack(spacing: 12) {
                    IconChip(systemImage: "checkmark", tint: Theme.lime, fill: Theme.lime.opacity(0.13))
                    VStack(alignment: .leading, spacing: 2) {
                        Text("没有进行中的下载").font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.text)
                        Text("新收藏会按来源设置自动存到 NAS。").font(.system(size: 11.5)).foregroundStyle(Theme.muted)
                    }
                    Spacer()
                }
                .card()
            }
            if progress.failedTotal > 0 {
                FailureSection(progress: progress) { await poller.refresh(client: model.client) }
            }
        } else {
            ProgressView().frame(maxWidth: .infinity, minHeight: 120)
        }
    }

    private var syncPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                IconChip(systemImage: healthIcon.name, tint: healthIcon.color, fill: healthIcon.color.opacity(0.13))
                VStack(alignment: .leading, spacing: 2) {
                    Text(healthTitle).font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.text)
                    Text(healthDetail).font(.system(size: 11.5)).foregroundStyle(Theme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            Button {
                Task { await sync() }
            } label: {
                HStack(spacing: 6) {
                    if syncing { ProgressView().controlSize(.small) }
                    Label("立即同步", systemImage: "arrow.clockwise")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glass)
            .controlSize(.large)
            .disabled(syncing)
            if let note { Text(note).font(.system(size: 11.5)).foregroundStyle(Theme.muted) }
        }
        .card()
    }

    @ViewBuilder
    private var history: some View {
        if let runs, !runs.isEmpty {
            let notable = runs.filter { $0.status != "completed" || $0.enqueued > 0 || $0.mode == "full" }.prefix(6)
            let quiet = runs.count - runs.filter { $0.status != "completed" || $0.enqueued > 0 || $0.mode == "full" }.count
            SectionHeader(title: "最近同步")
            VStack(spacing: 0) {
                if quiet > 0 {
                    row(title: "最近自动检查了 \(quiet) 次，都正常", detail: "没有发现需要下载的新收藏", badge: "正常", tint: Theme.lime)
                }
                ForEach(Array(notable.enumerated()), id: \.element.id) { index, run in
                    if index > 0 || quiet > 0 { Divider().overlay(Theme.line) }
                    row(
                        title: run.mode == "full" ? "全量核对" : run.enqueued > 0 ? "发现 \(run.enqueued) 个新收藏" : "增量同步",
                        detail: Format.dateTime(run.startedAt) + (Format.errorText(run.errorCode).map { " · \($0)" } ?? ""),
                        badge: runBadge(run.status).text,
                        tint: runBadge(run.status).color
                    )
                }
            }
            .card(radius: Theme.radiusInner, padding: EdgeInsets(top: 2, leading: 14, bottom: 2, trailing: 12))
        }
    }

    private func row(title: String, detail: String, badge: String, tint: Color) -> some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.system(size: 13, weight: .medium)).foregroundStyle(Theme.text).lineLimit(1)
                Text(detail).font(.system(size: 11)).foregroundStyle(Theme.muted).lineLimit(1)
            }
            Spacer(minLength: 4)
            Text(badge).font(.system(size: 11, weight: .semibold))
                .lineLimit(1).fixedSize()
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(tint.opacity(0.14), in: Capsule())
                .foregroundStyle(tint)
        }
        .padding(.vertical, 9)
    }

    private func runBadge(_ status: String) -> (text: String, color: Color) {
        switch status {
        case "completed": ("完成", Theme.lime)
        case "failed": ("失败", Theme.redText)
        case "running": ("进行中", Theme.violet4)
        case "partial": ("部分完成", Theme.amber)
        default: ("排队中", Theme.muted)
        }
    }

    private var healthIcon: (name: String, color: Color) {
        switch health?.state {
        case "ok": ("checkmark.seal", Theme.lime)
        case "syncing": ("arrow.triangle.2.circlepath", Theme.violet4)
        case "login_required": ("person.crop.circle.badge.exclamationmark", Theme.redText)
        case "failing", "stale": ("exclamationmark.triangle", Theme.amber)
        default: ("hourglass", Theme.muted)
        }
    }

    private var healthTitle: String {
        switch health?.state {
        case "ok": "同步正常"
        case "syncing": "正在同步收藏"
        case "login_required": "抖音登录已失效"
        // The browser probe also reports "failing" while recent runs succeeded;
        // name that cause so it doesn't contradict the run history below.
        case "failing" where health?.lastErrorCode == "BROWSER_DISCONNECTED": "后台浏览器没有响应"
        case "failing": "同步一直失败"
        case "stale": "同步好久没完成了"
        case "never": "还没同步过"
        case nil: "正在检查"
        default: health?.state ?? ""
        }
    }

    private var healthDetail: String {
        guard let health else { return " " }
        if health.state == "login_required" { return "请在电脑上打开抖藏家网页，重新扫码登录抖音。" }
        let interval = "每 \(health.intervalSeconds / 60) 分钟检查一次"
        if health.state == "failing" && health.lastErrorCode == "BROWSER_DISCONNECTED" {
            return "下次同步时会自动重启它 · 上次成功同步 \(Format.relative(health.lastSuccessAt))"
        }
        return "上次成功同步 \(Format.relative(health.lastSuccessAt)) · \(interval)"
    }

    private func load() async {
        if health == nil { health = model.client.cachedSyncHealth() }
        if runs == nil { runs = model.client.cachedSyncRuns() }
        if stats == nil { stats = model.client.cachedHome()?.stats }
        do {
            async let healthValue = model.client.syncHealth()
            async let runValues = model.client.syncRuns()
            async let homeValue = model.client.home()
            health = try await healthValue
            runs = try await runValues
            stats = (try? await homeValue)?.stats
        } catch {
            model.handle(error)
        }
        await poller.refresh(client: model.client)
    }

    private func sync() async {
        syncing = true
        defer { syncing = false }
        do {
            try await model.client.triggerSync()
            note = "已开始同步"
            try? await Task.sleep(for: .seconds(2))
            await load()
        } catch {
            model.handle(error)
            note = (error as? APIError)?.message ?? "无法开始同步"
        }
    }
}
