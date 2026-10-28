import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var confirmSignOut = false

    var body: some View {
        NavigationStack {
            List {
                Section("连接") {
                    LabeledContent("NAS 地址", value: model.serverAddress)
                    LabeledContent("管理员", value: model.username.isEmpty ? "—" : model.username)
                }
                Section {
                    Text("扫码登录抖音、相册整理和来源设置请在电脑上打开抖藏家网页操作。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Section {
                    Button("退出登录", role: .destructive) { confirmSignOut = true }
                }
                Section {
                    LabeledContent("版本", value: appVersion)
                }
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

    private var appVersion: String {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "?"
        let build = info?["CFBundleVersion"] as? String ?? "?"
        return "\(version) (\(build))"
    }
}
