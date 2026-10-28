import AVFoundation
import SwiftUI

@main
struct DouzangjiaApp: App {
    @State private var model = AppModel()

    init() {
        // Archived videos should be heard even with the ring/silent switch on.
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .tint(.brand)
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
            HomeView()
                .tabItem { Label("首页", systemImage: "house") }
                .tag(0)
            LibraryView()
                .tabItem { Label("作品", systemImage: "square.grid.3x3") }
                .tag(1)
            ActivityView()
                .tabItem { Label("下载", systemImage: "arrow.down.circle") }
                .tag(2)
        }
    }

    private static var initialTab: Int {
        #if DEBUG
        return UserDefaults.standard.integer(forKey: "devTab")
        #else
        return 0
        #endif
    }
}
