import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var confirmSignOut = false
    @State private var backup: BackupStatus?
    @State private var backingUp = false
    @State private var backupNote: String?
    @State private var settings: ServerSettings?
    @State private var storage: StorageUsage?
    @State private var barkURL = ""
    @State private var settingsNote: String?
    @State private var notifyNote: String?
    @State private var testing = false
    @State private var exporting = false
    @State private var exportNote: String?
    @State private var exportFiles: ShareFiles?

    private static let intervals: [(seconds: Int, title: String)] = [
        (300, "每 5 分钟"), (900, "每 15 分钟"), (1800, "每 30 分钟"), (3600, "每小时"), (21_600, "每 6 小时"),
    ]
    private static let events: [(key: String, title: String)] = [
        ("login_required", "抖音登录失效"), ("failing", "同步连续失败"), ("stale", "同步停止超过半小时"),
        ("disk_low", "NAS 剩余空间不足"), ("recovered", "问题恢复后通知一次"), ("creator_vanished", "有博主被封号或资料被重置"),
    ]

    var body: some View {
        NavigationStack {
            List {
                Section("连接") {
                    LabeledContent("NAS 地址", value: model.serverAddress)
                    LabeledContent("管理员", value: model.username.isEmpty ? "—" : model.username)
                }
                storageSection
                syncSection
                notificationSection
                Section {
                    if let latest = backup?.backups.first {
                        LabeledContent("最近一次", value: Format.relative(latest.createdAt))
                        LabeledContent("保留", value: "最近 \(backup?.keep ?? 7) 份 · 每份 \(Format.bytes(latest.bytes))")
                    } else {
                        Text(backup == nil ? "正在读取…" : "还没有自动备份，一小时内会做第一份。")
                            .foregroundStyle(Theme.muted)
                    }
                    Button {
                        Task { await runBackup() }
                    } label: {
                        HStack {
                            Text("立即备份")
                            if backingUp { Spacer(); ProgressView() }
                        }
                    }
                    .disabled(backingUp)
                } header: {
                    Text("数据库备份")
                } footer: {
                    Text(backupNote ?? backup?.lastError.map { "上次备份失败：\($0)" }
                         ?? "相册、标签、备注和精选只存在这个数据库里。NAS 每天自动备份一份并检查能正常打开，放在归档目录的 data/backups/ 下。")
                }
                Section {
                    Button {
                        Task { await exportCatalog() }
                    } label: {
                        HStack {
                            Text("导出全部作品清单")
                            if exporting { Spacer(); ProgressView() }
                        }
                    }
                    .disabled(exporting)
                } header: {
                    Text("带走数据")
                } footer: {
                    Text(exportNote ?? "一张表格（CSV）：每个作品的标题、博主、链接、标签、备注，以及存在 NAS 哪个文件。不含视频本身，可以存到“文件”或发给自己。")
                }
                Section {
                    Text("扫码登录抖音、相册整理和来源设置请在电脑上打开抖藏家网页操作。")
                        .font(.footnote)
                        .foregroundStyle(Theme.muted)
                }
                Section {
                    Button("退出登录", role: .destructive) { confirmSignOut = true }
                }
                Section {
                    LabeledContent("版本", value: appVersion)
                }
            }
            .task {
                async let backupStatus = try? model.client.backupStatus()
                async let serverSettings = try? model.client.serverSettings()
                async let usage = try? model.client.storage()
                backup = await backupStatus
                settings = await serverSettings
                storage = await usage
                barkURL = settings?.values.notifications["bark"]?["url"]?.stringValue ?? ""
            }
            .sheet(item: $exportFiles, onDismiss: { exportFiles?.cleanUp() }) { files in
                ShareSheet(items: files.urls)
                    .ignoresSafeArea()
                    .presentationDetents([.medium, .large])
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() } }
            }
            .confirmationDialog("退出后需要重新输入管理员密码。", isPresented: $confirmSignOut, titleVisibility: .visible) {
                Button("退出登录", role: .destructive) {
                    Task {
                        await model.signOut()
                        dismiss()
                    }
                }
            }
        }
    }

    // MARK: Storage

    @ViewBuilder
    private var storageSection: some View {
        Section {
            if let storage {
                if let disk = storage.disk {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(alignment: .firstTextBaseline) {
                            Text("剩余 \(Format.bytes(disk.freeBytes))").font(.headline)
                                .foregroundStyle(disk.low ? Theme.redText : Theme.text)
                            Spacer()
                            Text("共 \(Format.bytes(disk.totalBytes))").font(.footnote).foregroundStyle(Theme.muted)
                        }
                        StorageBar(disk: disk, archive: storage.media.bytes)
                        HStack(spacing: 14) {
                            legend(Theme.violet2, "抖藏家")
                            legend(Theme.gray, "其他文件")
                            legend(Theme.panel3, "空闲")
                        }
                        .font(.caption)
                    }
                    .padding(.vertical, 4)
                }
                LabeledContent("视频", value: Format.bytes(storage.media.videoBytes))
                LabeledContent("图集图片", value: Format.bytes(storage.media.imageBytes))
                if storage.media.otherBytes > 0 {
                    LabeledContent("配乐等其他", value: Format.bytes(storage.media.otherBytes))
                }
                LabeledContent("数据库", value: Format.bytes(storage.database.bytes))
                LabeledContent("数据库备份", value: "\(storage.backups.count ?? 0) 份 · \(Format.bytes(storage.backups.bytes))")
                if storage.quarantine.bytes > 0 {
                    LabeledContent("损坏文件隔离区", value: "\(storage.quarantine.files ?? 0) 个 · \(Format.bytes(storage.quarantine.bytes))")
                }
            } else {
                Text("正在读取…").foregroundStyle(Theme.muted)
            }
        } header: {
            Text("存储")
        } footer: {
            if storage?.disk?.low == true {
                Text("NAS 空间快满了，新作品可能下载失败。可以清理不需要的文件，或换更大的硬盘。")
            } else {
                Text("“抖藏家”是 \(storage.map { "\($0.media.files) 个已存文件" } ?? "已存文件") 占的空间。")
            }
        }
    }

    private func legend(_ color: Color, _ title: String) -> some View {
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(title).foregroundStyle(Theme.muted)
        }
    }

    // MARK: Sync

    @ViewBuilder
    private var syncSection: some View {
        Section {
            if let values = settings?.values {
                Picker("自动同步", selection: Binding(
                    get: { values.syncIntervalSeconds },
                    set: { value in Task { await update(["sync_interval_seconds": value]) } }
                )) {
                    ForEach(Self.intervals, id: \.seconds) { Text($0.title).tag($0.seconds) }
                    if !Self.intervals.contains(where: { $0.seconds == values.syncIntervalSeconds }) {
                        Text("每 \(values.syncIntervalSeconds / 60) 分钟").tag(values.syncIntervalSeconds)
                    }
                }
                Stepper(value: Binding(
                    get: { values.downloadWorkers },
                    set: { value in Task { await update(["download_workers": value]) } }
                ), in: 1...4) {
                    LabeledContent("同时下载", value: "\(values.downloadWorkers) 个")
                }
            } else {
                Text("正在读取…").foregroundStyle(Theme.muted)
            }
        } header: {
            Text("同步与下载")
        } footer: {
            Text(settingsNote ?? "多久去抖音看一次新收藏。同时下载越多越快，但更容易被抖音限流。")
        }
    }

    // MARK: Notifications

    private var notifications: JSONValue { settings?.values.notifications ?? .object([:]) }

    private var channelNames: [String] {
        var names: [String] = []
        if !(notifications["bark"]?["url"]?.stringValue ?? "").isEmpty { names.append("Bark") }
        if !(notifications["telegram"]?["bot_token"]?.stringValue ?? "").isEmpty,
           !(notifications["telegram"]?["chat_id"]?.stringValue ?? "").isEmpty { names.append("Telegram") }
        if !(notifications["webhook"]?["url"]?.stringValue ?? "").isEmpty { names.append("Webhook") }
        return names
    }

    @ViewBuilder
    private var notificationSection: some View {
        Section {
            if settings != nil {
                LabeledContent("已开启的渠道", value: channelNames.isEmpty ? "还没有" : channelNames.joined(separator: "、"))
                TextField("Bark 推送地址", text: $barkURL)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .submitLabel(.done)
                    .onSubmit { Task { await saveBark() } }
                ForEach(Self.events, id: \.key) { event in
                    Toggle(event.title, isOn: Binding(
                        get: { notifications["events"]?[event.key]?.boolValue ?? true },
                        set: { value in Task { await setEvent(event.key, value) } }
                    ))
                    .disabled(channelNames.isEmpty)
                }
                Button {
                    Task { await sendTest() }
                } label: {
                    HStack {
                        Text("发送测试通知")
                        if testing { Spacer(); ProgressView() }
                    }
                }
                .disabled(channelNames.isEmpty || testing)
            } else {
                Text("正在读取…").foregroundStyle(Theme.muted)
            }
        } header: {
            Text("通知")
        } footer: {
            Text(notifyNote ?? "在 iPhone 上装 Bark，把它给的推送地址填在这里，NAS 出问题时会推送到手机。Telegram 和 Webhook 请在网页的设置页填写。")
        }
    }

    private func update(_ changes: [String: Any]) async {
        do {
            settings = try await model.client.updateSettings(changes)
            settingsNote = nil
        } catch {
            settingsNote = "没有保存：\((error as? APIError)?.message ?? error.localizedDescription)"
        }
    }

    /// The server replaces the whole notifications object, so send every field back.
    private func saveNotifications(_ next: JSONValue) async {
        do {
            settings = try await model.client.updateSettings(["notifications": next.foundation])
            notifyNote = nil
        } catch {
            notifyNote = "没有保存：\((error as? APIError)?.message ?? error.localizedDescription)"
        }
    }

    private func editing(_ change: (inout [String: JSONValue]) -> Void) -> JSONValue {
        var fields: [String: JSONValue] = if case .object(let existing) = notifications { existing } else { [:] }
        change(&fields)
        return .object(fields)
    }

    private func saveBark() async {
        let url = barkURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard url != (notifications["bark"]?["url"]?.stringValue ?? "") else { return }
        if !url.isEmpty, !url.hasPrefix("https://"), !url.hasPrefix("http://") {
            notifyNote = "Bark 地址要以 https:// 开头，比如 https://api.day.app/你的设备Key"
            return
        }
        await saveNotifications(editing { $0["bark"] = .object(["url": .string(url)]) })
        if notifyNote == nil { notifyNote = url.isEmpty ? "已关闭 Bark 推送。" : "已保存，点“发送测试通知”试试。" }
    }

    private func setEvent(_ key: String, _ on: Bool) async {
        await saveNotifications(editing { fields in
            var events: [String: JSONValue] = if case .object(let existing) = fields["events"] { existing } else { [:] }
            events[key] = .bool(on)
            fields["events"] = .object(events)
        })
    }

    private func sendTest() async {
        await saveBark()
        testing = true
        defer { testing = false }
        do {
            let results = try await model.client.testNotifications()
            let names = ["bark": "Bark", "telegram": "Telegram", "webhook": "Webhook"]
            let failed = results.filter { $0.value != "ok" }.keys.sorted().map { names[$0] ?? $0 }
            let sent = results.filter { $0.value == "ok" }.keys.sorted().map { names[$0] ?? $0 }
            // Only claim success for channels that actually accepted the message.
            if failed.isEmpty {
                notifyNote = "已通过 \(sent.joined(separator: "、")) 发送，看看手机有没有收到。"
            } else {
                notifyNote = "\(failed.joined(separator: "、")) 没发出去，请检查推送地址是否正确、NAS 能否上网。"
                    + (sent.isEmpty ? "" : "\(sent.joined(separator: "、")) 已发送。")
            }
        } catch {
            notifyNote = "发送失败：\((error as? APIError)?.message ?? error.localizedDescription)"
        }
    }

    private func exportCatalog() async {
        guard let url = model.client.resolve("/api/export/catalog.csv") else { return }
        exporting = true
        exportNote = nil
        defer { exporting = false }
        let day = Date().formatted(.verbatim("\(year: .defaultDigits)\(month: .twoDigits)\(day: .twoDigits)",
                                             timeZone: .current, calendar: .current))
        do {
            let file = try await model.client.downloadFile(url, named: "抖藏家作品清单-\(day).csv")
            exportFiles = ShareFiles(urls: [file])
        } catch is CancellationError {
        } catch {
            exportNote = "导出没有完成：\(error.localizedDescription)"
        }
    }

    private func runBackup() async {
        backingUp = true
        defer { backingUp = false }
        do {
            backup = try await model.client.backupNow()
            backupNote = "已备份数据库。"
        } catch {
            backupNote = "备份没有完成：\(error.localizedDescription)"
        }
    }

    private var appVersion: String {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "?"
        let build = info?["CFBundleVersion"] as? String ?? "?"
        return "\(version) (\(build))"
    }
}

/// Disk at a glance: this archive, everything else on the volume, and free space.
private struct StorageBar: View {
    let disk: StorageUsage.Disk
    let archive: Int

    var body: some View {
        GeometryReader { proxy in
            let total = max(1, Double(disk.totalBytes))
            let mine = min(Double(archive), Double(disk.usedBytes)) / total
            let others = max(0, Double(disk.usedBytes) - Double(archive)) / total
            HStack(spacing: 2) {
                Theme.violet2.frame(width: proxy.size.width * mine)
                Theme.gray.frame(width: proxy.size.width * others)
                Theme.panel3
            }
            .clipShape(Capsule())
        }
        .frame(height: 10)
        .accessibilityElement()
        .accessibilityLabel("已用 \(Format.bytes(disk.usedBytes))，共 \(Format.bytes(disk.totalBytes))")
    }
}
