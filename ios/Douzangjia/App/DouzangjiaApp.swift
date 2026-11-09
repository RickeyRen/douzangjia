import AVFoundation
import SwiftUI

@main
struct DouzangjiaApp: App {
    @State private var model = AppModel()

    init() {
        // Archived videos should be heard even with the ring/silent switch on.
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
        // Thumbnails are small and immutable; a roomy disk cache makes the grid instant on return.
        URLCache.shared = URLCache(memoryCapacity: 32 * 1024 * 1024, diskCapacity: 1024 * 1024 * 1024)
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                // System controls (alert buttons, links) need a lighter violet to read on near-black;
                // filled buttons use Theme.violet directly.
                .tint(Theme.violet3)
                .preferredColorScheme(.dark)
        }
    }
}

struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Group {
            switch model.phase {
            case .checking:
                ProgressView("正在连接 NAS…")
                    .foregroundStyle(Theme.muted)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .screenBackground()
                    .task { await model.restore() }
            case .signedOut:
                LoginView()
            case .signedIn:
                MainTabView()
            }
        }
        .animation(.default, value: model.phase)
    }
}

struct MainTabView: View {
    @State private var tab = MainTabView.initialTab
    @State private var keyboardShown = false

    private let items = [
        DZTabItem(id: 0, title: "首页", systemImage: "house"),
        DZTabItem(id: 1, title: "作品", systemImage: "square.grid.2x2"),
        DZTabItem(id: 2, title: "下载", systemImage: "arrow.down.to.line"),
    ]

    var body: some View {
        // The system TabView still owns each tab's lifetime (pollers start/stop on
        // appear/disappear); only its bar is replaced by the floating capsule.
        TabView(selection: $tab) {
            HomeView()
                .tabChrome()
                .tag(0)
            LibraryView()
                .tabChrome()
                .tag(1)
            ActivityView()
                .tabChrome()
                .tag(2)
        }
        .environment(\.selectTab) { tab = $0 }
        .overlay(alignment: .bottom) {
            ZStack(alignment: .bottom) {
                LinearGradient(
                    stops: [.init(color: Theme.bg.opacity(0), location: 0),
                            .init(color: Theme.bg.opacity(0.9), location: 0.55),
                            .init(color: Theme.bg, location: 1)],
                    startPoint: .top, endPoint: .bottom
                )
                .frame(height: 110)
                .allowsHitTesting(false)
                DZTabBar(selection: $tab, items: items)
                    .padding(.bottom, 26)
            }
            .ignoresSafeArea(.container, edges: .bottom)
            .ignoresSafeArea(.keyboard)
            // Typing in search should not push the bar up onto the keyboard.
            .opacity(keyboardShown ? 0 : 1)
            .allowsHitTesting(!keyboardShown)
        }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillShowNotification)) { _ in
            keyboardShown = true
        }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)) { _ in
            keyboardShown = false
        }
        .screenBackground()
    }

    private static var initialTab: Int {
        #if DEBUG
        return UserDefaults.standard.integer(forKey: "devTab")
        #else
        return 0
        #endif
    }
}

private extension View {
    func tabChrome() -> some View {
        toolbar(.hidden, for: .tabBar)
    }
}
