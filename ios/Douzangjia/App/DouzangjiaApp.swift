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
                // System controls (tab selection, alert buttons, links) need a lighter violet to read
                // on near-black; prominent buttons tint themselves with Theme.violet2.
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

    var body: some View {
        TabView(selection: $tab) {
            Tab("首页", systemImage: "house", value: 0) { HomeView() }
            Tab("作品", systemImage: "square.grid.2x2", value: 1) { LibraryView() }
            Tab("下载", systemImage: "arrow.down.to.line", value: 2) { ActivityView() }
        }
        .environment(\.selectTab) { tab = $0 }
    }

    private static var initialTab: Int {
        #if DEBUG
        return UserDefaults.standard.integer(forKey: "devTab")
        #else
        return 0
        #endif
    }
}
