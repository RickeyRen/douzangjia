import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var confirmSignOut = false
    @State private var backup: BackupStatus?
    @State private var backingUp = false
    @State private var backupNote: String?

    var body: some View {
        NavigationStack {
            List {
                Section("连接") {
                    LabeledContent("NAS 地址", value: model.serverAddress)
                    LabeledContent("管理员", value: model.username.isEmpty ? "—" : model.username)
                }
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
            .task { backup = try? await model.client.backupStatus() }
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
