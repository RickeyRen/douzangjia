import AVKit
import SwiftUI

/// Full-screen vertical pager, like scrolling Douyin itself.
struct PlayerView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var items: [FeedItem]
    @State private var current: String?
    var onItemChange: (FeedItem) -> Void = { _ in }

    init(items: [FeedItem], startIndex: Int, onItemChange: @escaping (FeedItem) -> Void = { _ in }) {
        _items = State(initialValue: items)
        _current = State(initialValue: items.indices.contains(startIndex) ? items[startIndex].id : items.first?.id)
        self.onItemChange = onItemChange
    }

    var body: some View {
        // Tapping the author opens their archive on top of the player, and Back
        // returns to the same video, as on Douyin.
        NavigationStack {
            pager
                .toolbar(.hidden, for: .navigationBar)
                .navigationDestination(for: CreatorRoute.self) { CreatorArchiveView(creatorId: $0.id) }
        }
    }

    private var pager: some View {
        ScrollViewReader { proxy in
            ScrollView(.vertical) {
                LazyVStack(spacing: 0) {
                    ForEach($items) { $item in
                        PlayerPage(item: $item, isCurrent: current == item.id, onItemChange: onItemChange)
                            .containerRelativeFrame([.horizontal, .vertical])
                            .id(item.id)
                    }
                }
                .scrollTargetLayout()
            }
            .scrollTargetBehavior(.paging)
            .scrollPosition(id: $current)
            .scrollIndicators(.hidden)
            // The lazy stack ignores the initial position until it has laid out.
            .onAppear { if let current { proxy.scrollTo(current, anchor: .top) } }
        }
        .ignoresSafeArea()
        .background(.black)
        .environment(\.colorScheme, .dark)
        .overlay(alignment: .topLeading) {
            Button { dismiss() } label: {
                Image(systemName: "xmark")
                    .font(.headline)
                    .foregroundStyle(.white)
                    .frame(width: 40, height: 40)
                    .background(.black.opacity(0.4), in: Circle())
            }
            .accessibilityLabel("关闭")
            .padding(.leading, 16)
            .padding(.top, 8)
        }
        .statusBarHidden()
    }
}

private struct PlayerPage: View {
    @Environment(AppModel.self) private var model
    @Binding var item: FeedItem
    let isCurrent: Bool
    let onItemChange: (FeedItem) -> Void
    @State private var queued = false
    @State private var message: String?
    @State private var video = VideoController()

    private var playableURL: URL? {
        guard !item.isGallery, let file = item.media.first(where: \.isVideo) else { return nil }
        return model.client.resolve(file.url)
    }

    var body: some View {
        ZStack(alignment: .bottom) {
            Color.black
            content
            details
            if playableURL != nil {
                VideoProgressBar(video: video)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 22)
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if let url = playableURL {
            VideoPage(video: video, url: url, cookies: model.client.cookies, isCurrent: isCurrent)
        } else if item.isGallery, !item.media.isEmpty {
            TabView {
                ForEach(item.media, id: \.id) { file in
                    RemoteImage(path: file.url, contentMode: .fit)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .always))
        } else {
            // Not on the NAS yet: show the Douyin cover and offer to save it.
            ZStack {
                // No placeholder icon: it would sit right under the status text.
                RemoteImage(path: item.coverUrl, contentMode: .fit, failureIcon: "").opacity(0.5)
                VStack(spacing: 14) {
                    Image(systemName: "icloud").font(.system(size: 40)).foregroundStyle(Theme.violet4)
                    Text(statusText).font(.headline).multilineTextAlignment(.center).padding(.horizontal, 24)
                    if item.local?.state != "downloading" && !item.videoIsLost {
                        Button {
                            Task { await save() }
                        } label: {
                            Label(queued ? "已加入下载" : "存到 NAS", systemImage: "icloud.and.arrow.down")
                        }
                        .buttonStyle(.glassProminent)
                        .tint(Theme.violet2)
                        .controlSize(.large)
                        .disabled(queued)
                    }
                    if let message { Text(message).font(.footnote).opacity(0.8) }
                }
                .foregroundStyle(.white)
            }
        }
    }

    private var statusText: String {
        if item.videoIsLost { return "视频没有存下来，抖音上也看不到了" }
        if item.videoIsAtRisk && item.local?.state != "downloading" { return "视频还没存下来，抖音上可能很快就看不到了" }
        return switch item.local?.state {
        case "downloading": "正在存到 NAS…"
        case "retry": "下载遇到问题，稍后会自动重试"
        case "failed": "下载失败"
        default: "还没存到 NAS"
        }
    }

    private var creatorRoute: CreatorRoute? {
        item.creator?.id.map { CreatorRoute(id: $0) }
    }

    private var details: some View {
        HStack(alignment: .bottom, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                if let creatorRoute {
                    NavigationLink(value: creatorRoute) {
                        Text("@\(item.creator?.nickname ?? item.author)").font(.headline)
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("打开博主存档主页")
                } else {
                    Text("@\(item.author)").font(.headline)
                }
                if item.isSaved {
                    Pill(text: "已存到 NAS", systemImage: "checkmark", style: .tag)
                }
                if !item.description.isEmpty {
                    Text(item.description).font(.subheadline).lineLimit(3)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            VStack(spacing: 18) {
                if let creatorRoute {
                    NavigationLink(value: creatorRoute) {
                        CreatorAvatar(path: item.creator?.avatarUrl, size: 48)
                            .overlay(Circle().strokeBorder(.white, lineWidth: 1.5))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("打开 \(item.creator?.nickname ?? item.author) 的主页")
                }
                Button {
                    Task { await toggleStar() }
                } label: {
                    Image(systemName: item.starred == true ? "star.fill" : "star")
                        .font(.title2)
                        .foregroundStyle(item.starred == true ? Theme.lime : .white)
                        .frame(width: 48, height: 48)
                        .background(item.starred == true ? Theme.violet.opacity(0.85) : .black.opacity(0.35), in: Circle())
                        .overlay(Circle().strokeBorder(Theme.line2, lineWidth: 1))
                }
                .accessibilityLabel(item.starred == true ? "取消精选" : "加入精选")
            }
        }
        .foregroundStyle(.white)
        .padding(.horizontal, 16)
        .padding(.bottom, 48)
        .padding(.top, 60)
        .background(LinearGradient(colors: [.clear, .black.opacity(0.7)], startPoint: .top, endPoint: .bottom).allowsHitTesting(false))
    }

    private func toggleStar() async {
        let next = !(item.starred ?? false)
        item.starred = next
        do {
            try await model.client.setStar(item.id, starred: next)
            onItemChange(item)
        } catch {
            item.starred = !next
            model.handle(error)
        }
    }

    private func save() async {
        do {
            try await model.client.archiveItem(item.id)
            queued = true
            message = "下载好后就能在这里播放"
        } catch {
            model.handle(error)
            message = (error as? APIError)?.message ?? "加入下载失败"
        }
    }
}

/// Owns one page's AVPlayer so the video surface and the progress bar share it.
@Observable
final class VideoController {
    private(set) var player: AVPlayer?
    private(set) var paused = false
    private(set) var duration: Double = 0
    var progress: Double = 0
    var scrubbing = false
    private var timeObserver: Any?
    private var endObserver: NSObjectProtocol?

    func prepare(url: URL, cookies: [HTTPCookie]) {
        guard player == nil else { return }
        // AVPlayer does not read URLSession's cookie store; hand it the session.
        let asset = AVURLAsset(url: url, options: [AVURLAssetHTTPCookiesKey: cookies])
        let item = AVPlayerItem(asset: asset)
        let next = AVPlayer(playerItem: item)
        next.actionAtItemEnd = .none
        endObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main
        ) { [weak next] _ in
            // Loops like Douyin until the user swipes on.
            next?.seek(to: .zero)
            next?.play()
        }
        timeObserver = next.addPeriodicTimeObserver(
            forInterval: CMTime(value: 1, timescale: 10), queue: .main
        ) { [weak self, weak next] time in
            guard let self, let next, !self.scrubbing else { return }
            let total = next.currentItem?.duration.seconds ?? 0
            if total.isFinite, total > 0 {
                self.duration = total
                self.progress = min(1, max(0, time.seconds / total))
            }
        }
        player = next
    }

    func setActive(_ active: Bool, restart: Bool = false) {
        guard let player else { return }
        if active {
            if restart { player.seek(to: .zero) }
            player.play()
            paused = false
        } else {
            player.pause()
        }
    }

    func togglePlay() {
        guard let player else { return }
        if player.timeControlStatus == .paused {
            player.play()
            paused = false
        } else {
            player.pause()
            paused = true
        }
    }

    func seek(to fraction: Double) {
        guard let player, duration > 0 else { return }
        progress = min(1, max(0, fraction))
        player.seek(
            to: CMTime(seconds: progress * duration, preferredTimescale: 600),
            toleranceBefore: .zero, toleranceAfter: .zero
        )
    }

    deinit {
        if let timeObserver { player?.removeTimeObserver(timeObserver) }
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }
    }
}

private struct VideoPage: View {
    let video: VideoController
    let url: URL
    let cookies: [HTTPCookie]
    let isCurrent: Bool

    var body: some View {
        ZStack {
            if let player = video.player {
                PlayerSurface(player: player)
            } else {
                ProgressView().tint(Theme.violet3)
            }
            if video.paused && isCurrent {
                Image(systemName: "play.fill")
                    .font(.system(size: 64))
                    .foregroundStyle(.white.opacity(0.8))
                    .shadow(color: .black.opacity(0.5), radius: 12)
                    .allowsHitTesting(false)
                    .transition(.opacity.combined(with: .scale(scale: 1.3)))
            }
        }
        .contentShape(Rectangle())
        // Single tap pauses or resumes, like Douyin; no system controls appear.
        .onTapGesture { withAnimation(.easeOut(duration: 0.15)) { video.togglePlay() } }
        .accessibilityAddTraits(.isButton)
        .accessibilityLabel(video.paused ? "继续播放" : "暂停")
        .onAppear {
            video.prepare(url: url, cookies: cookies)
            // Also resumes after coming back from the creator page.
            if isCurrent { video.setActive(true) }
        }
        .onChange(of: isCurrent) { _, current in
            // Swiping back to a video starts it over.
            video.setActive(current, restart: current)
        }
        .onDisappear { video.setActive(false) }
    }
}

/// AVPlayerLayer without AVKit's controls, so taps reach our own gesture.
private struct PlayerSurface: UIViewRepresentable {
    let player: AVPlayer

    func makeUIView(context: Context) -> PlayerLayerView {
        let view = PlayerLayerView()
        view.playerLayer.videoGravity = .resizeAspect
        view.playerLayer.player = player
        return view
    }

    func updateUIView(_ view: PlayerLayerView, context: Context) {
        if view.playerLayer.player !== player { view.playerLayer.player = player }
    }
}

private final class PlayerLayerView: UIView {
    override class var layerClass: AnyClass { AVPlayerLayer.self }
    var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }
}

/// Douyin-style hairline progress: thickens and shows the time while dragged.
private struct VideoProgressBar: View {
    let video: VideoController

    var body: some View {
        VStack(spacing: 8) {
            if video.scrubbing {
                Text("\(clock(video.progress * video.duration)) / \(clock(video.duration))")
                    .font(.system(.title3, design: .rounded).monospacedDigit().weight(.semibold))
                    .foregroundStyle(.white)
                    .shadow(color: .black.opacity(0.6), radius: 6)
            }
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule().fill(.white.opacity(0.25))
                    Capsule().fill(.white.opacity(video.scrubbing ? 1 : 0.8))
                        .frame(width: proxy.size.width * video.progress)
                }
                .frame(height: video.scrubbing ? 6 : 2)
                .frame(maxHeight: .infinity, alignment: .center)
                .contentShape(Rectangle())
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { value in
                            if !video.scrubbing { withAnimation(.easeOut(duration: 0.12)) { video.scrubbing = true } }
                            video.progress = min(1, max(0, value.location.x / max(1, proxy.size.width)))
                        }
                        .onEnded { value in
                            video.seek(to: value.location.x / max(1, proxy.size.width))
                            withAnimation(.easeOut(duration: 0.2)) { video.scrubbing = false }
                        }
                )
            }
            .frame(height: 24)
        }
        .accessibilityElement()
        .accessibilityLabel("播放进度")
        .accessibilityValue("\(clock(video.progress * video.duration)) / \(clock(video.duration))")
        .accessibilityAdjustableAction { direction in
            let step = video.duration > 0 ? 5 / video.duration : 0
            video.seek(to: video.progress + (direction == .increment ? step : -step))
        }
    }

    private func clock(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds > 0 else { return "0:00" }
        let total = Int(seconds.rounded())
        return String(format: "%d:%02d", total / 60, total % 60)
    }
}
