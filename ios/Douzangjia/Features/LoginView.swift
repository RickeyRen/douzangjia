import SwiftUI

struct LoginView: View {
    @Environment(AppModel.self) private var model
    @State private var server = ""
    @State private var username = ""
    @State private var password = ""
    @State private var pending = false
    @State private var error: String?
    @FocusState private var focus: Field?

    private enum Field { case server, username, password }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    VStack(spacing: 10) {
                        Image("AppIconPreview")
                            .resizable()
                            .frame(width: 72, height: 72)
                            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                        Text("抖藏家").font(.title2.bold())
                        Text("连上你 NAS 上的抖音收藏库").font(.subheadline).foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                    .listRowBackground(Color.clear)
                }

                Section {
                    TextField("192.168.0.6:8099", text: $server)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($focus, equals: .server)
                        .submitLabel(.next)
                        .onSubmit { focus = .username }
                } header: {
                    Text("NAS 地址")
                } footer: {
                    Text("在家里用局域网地址；在外面需要先连上能访问 NAS 的 VPN。")
                }

                Section("本地管理员") {
                    TextField("用户名", text: $username)
                        .textContentType(.username)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($focus, equals: .username)
                        .submitLabel(.next)
                        .onSubmit { focus = .password }
                    SecureField("密码", text: $password)
                        .textContentType(.password)
                        .focused($focus, equals: .password)
                        .submitLabel(.go)
                        .onSubmit { Task { await submit() } }
                }

                if let error {
                    Section {
                        Label(error, systemImage: "exclamationmark.triangle.fill")
                            .foregroundStyle(.red)
                            .font(.subheadline)
                    }
                }

                Section {
                    Button {
                        Task { await submit() }
                    } label: {
                        HStack {
                            Spacer()
                            if pending { ProgressView().padding(.trailing, 6) }
                            Text(pending ? "正在登录…" : "登录").bold()
                            Spacer()
                        }
                    }
                    .disabled(pending || username.isEmpty || password.isEmpty || server.isEmpty)
                }
            }
            .navigationTitle("登录")
            .navigationBarTitleDisplayMode(.inline)
            .onAppear {
                if server.isEmpty { server = model.serverAddress }
                if username.isEmpty { username = model.username }
                focus = username.isEmpty ? .username : .password
            }
        }
    }

    private func submit() async {
        guard !pending else { return }
        pending = true
        error = nil
        defer { pending = false }
        do {
            try await model.signIn(server: server, username: username, password: password)
        } catch let apiError as APIError {
            switch apiError.status {
            case 401: error = "用户名或密码不对。"
            case 429: error = "尝试次数太多，请稍后再试。"
            default: error = apiError.message
            }
        } catch {
            self.error = error.localizedDescription
        }
    }
}
