import SwiftUI

struct ActivityView: View {
    @Environment(AppModel.self) private var model
    @State private var poller = ProgressPoller()
    @State private var health: SyncHealth?
    @State private var runs: [SyncRun]?
    @State private var syncing = false
    @State private var note: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    downloads
                    syncPanel
                    history
                }
                .padding(16)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("下载与同步")
            .refreshable { await load() }
            .task { await load() }
            .onAppear { poller.start(client: model.client, onError: model.handle) }
            .onDisappear { poller.stop() }
        }
    }

    @ViewBuilder
    private var downloads: some View {
        if let progress = poller.progress {
            if let active = progress.active {
                DownloadProgressCard(active: active) { await poller.refresh(client: model.client) }
            } else {
                HStack(spacing: 12) {
                    Image(systemName: "checkmark.circle.fill").font(.title2).foregroundStyle(.green)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("没有进行中的下载").font(.headline)
                        Text("新收藏会按来源设置自动存到 NAS。").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .padding(16)
                .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
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
                Image(systemName: healthIcon.name)
                    .font(.title2)
                    .foregroundStyle(healthIcon.color)
                VStack(alignment: .leading, spacing: 2) {
                    Text(healthTitle).font(.headline)
                    Text(healthDetail).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
            }
            Button {
                Task { await sync() }
            } label: {
                HStack {
                    if syncing { ProgressView() }
                    Label("立即同步", systemImage: "arrow.clockwise")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .disabled(syncing)
            if let note { Text(note).font(.caption).foregroundStyle(.secondary) }
        }
        .padding(16)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    @ViewBuilder
    private var history: some View {
        if let runs {
            let notable = runs.filter { $0.status != "completed" || $0.enqueued > 0 || $0.mode == "full" }.prefix(6)
            let quiet = runs.count - runs.filter { $0.status != "completed" || $0.enqueued > 0 || $0.mode == "full" }.count
            VStack(alignment: .leading, spacing: 10) {
                Text("最近同步").font(.headline)
                if quiet > 0 {
                    row(title: "最近自动检查了 \(quiet) 次，都正常", detail: "没有发现需要下载的新收藏", badge: "正常", tint: .green)
                }
                ForEach(Array(notable)) { run in
                    row(
                        title: run.mode == "full" ? "全量核对" : run.enqueued > 0 ? "发现 \(run.enqueued) 个新收藏" : "增量同步",
                        detail: Format.dateTime(run.startedAt) + (Format.errorText(run.errorCode).map { " · \($0)" } ?? ""),
                        badge: runBadge(run.status).text,
                        tint: runBadge(run.status).color
                    )
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
    }

    private func row(title: String, detail: String, badge: String, tint: Color) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.weight(.medium))
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Text(badge).font(.caption.weight(.semibold))
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(tint.opacity(0.15), in: Capsule())
                .foregroundStyle(tint)
        }
    }

    private func runBadge(_ status: String) -> (text: String, color: Color) {
        switch status {
        case "completed": ("完成", .green)
        case "failed": ("失败", .red)
        case "running": ("进行中", .blue)
        case "partial": ("部分完成", .orange)
        default: ("排队中", .secondary)
        }
    }

    private var healthIcon: (name: String, color: Color) {
        switch health?.state {
        case "ok": ("checkmark.seal.fill", .green)
        case "syncing": ("arrow.triangle.2.circlepath.circle.fill", .blue)
        case "login_required": ("person.crop.circle.badge.exclamationmark", .red)
        case "failing", "stale": ("exclamationmark.triangle.fill", .orange)
        default: ("hourglass", .secondary)
        }
    }

    private var healthTitle: String {
        switch health?.state {
        case "ok": "同步正常"
        case "syncing": "正在同步收藏"
        case "login_required": "抖音登录已失效"
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
        return "上次成功同步 \(Format.relative(health.lastSuccessAt)) · \(interval)"
    }

    private func load() async {
        do {
            async let healthValue = model.client.syncHealth()
            async let runValues = model.client.syncRuns()
            health = try await healthValue
            runs = try await runValues
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
