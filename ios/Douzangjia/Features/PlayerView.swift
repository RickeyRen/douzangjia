import AVKit
import SwiftUI

/// Full-screen vertical pager, like scrolling Douyin itself.
struct PlayerView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppModel.self) private var model
    /// One player per nearby work, so the next swipe finds its video already buffered.
    @State private var pool = VideoPool()
    @State private var items: [FeedItem]
    @State private var current: String?
    /// Placed on the tapped work before the first layout. Scrolling there from
    /// onAppear raced the lazy stack: opening the second work showed the first
    /// one, frozen, because the page on screen was not the "current" one.
    @State private var position: ScrollPosition
    /// The page actually on screen, as the scroll view reports it.
    @State private var visible: String?
    @State private var galleryZoomed = false
    var onItemChange: (FeedItem) -> Void = { _ in }

    init(items: [FeedItem], startIndex: Int, onItemChange: @escaping (FeedItem) -> Void = { _ in }) {
        _items = State(initialValue: items)
        let start = items.indices.contains(startIndex) ? items[startIndex].id : items.first?.id
        _current = State(initialValue: start)
        _position = State(initialValue: start.map { ScrollPosition(id: $0, anchor: .top) } ?? ScrollPosition(idType: String.self))
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
        ScrollView(.vertical) {
            LazyVStack(spacing: 0) {
                ForEach($items) { $item in
                    PlayerPage(item: $item, isCurrent: current == item.id, video: pool.controller(for: item.id), galleryZoomed: $galleryZoomed, onItemChange: onItemChange)
                        .containerRelativeFrame([.horizontal, .vertical])
                        .id(item.id)
                }
            }
            .scrollTargetLayout()
        }
        .scrollTargetBehavior(.paging)
        // A zoomed-in image pans instead of moving to the next item.
        .scrollDisabled(galleryZoomed)
        .scrollPosition($position)
        .onChange(of: position.viewID(type: String.self)) { _, id in
            if let id { current = id }
        }
        .onChange(of: current, initial: true) { _, _ in warmUp() }
        // The paging stack can still land on the first page while it lays out;
        // put it back on the tapped work until the two agree.
        .task {
            guard let start = current else { return }
            for _ in 0..<5 {
                try? await Task.sleep(for: .milliseconds(120))
                if visible == start { return }
                position.scrollTo(id: start, anchor: .top)
            }
        }
        .onScrollTargetVisibilityChange(idType: String.self, threshold: 0.6) { ids in
            visible = ids.first
        }
        .scrollIndicators(.hidden)
        .ignoresSafeArea()
        .background(.black)
        .environment(\.colorScheme, .dark)
        .overlay(alignment: .topLeading) {
            Button { dismiss() } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(.white)
                    .shadow(color: .black.opacity(0.45), radius: 4, y: 1)
                    .frame(width: 44, height: 44)
                    .contentShape(Rectangle())
            }
            .accessibilityLabel("返回")
            .padding(.leading, 8)
            .padding(.top, 8)
        }
        .statusBarHidden()
        .onDisappear { pool.removeAll() }
    }

    /// Buffers the saved neighbours of the work on screen and lets go of far ones.
    /// Works not on the NAS yet are left alone: buffering them would ask Douyin
    /// for videos that may never be watched.
    private func warmUp() {
        guard let current, let index = items.firstIndex(where: { $0.id == current }) else { return }
        let window = max(0, index - 2)...min(items.count - 1, index + 3)
        pool.keep(Set(items[window].map(\.id)))
        for offset in [1, -1, 2] {
            let neighbour = index + offset
            guard items.indices.contains(neighbour),
                  let file = items[neighbour].media.first(where: \.isVideo),
                  let url = model.client.resolve(file.url) else { continue }
            pool.controller(for: items[neighbour].id).preload(url: url, cookies: model.client.cookies)
        }
    }
}

/// Players for the works around the one on screen, keyed by work id.
@MainActor
final class VideoPool {
    private var controllers: [String: VideoController] = [:]

    func controller(for id: String) -> VideoController {
        if let existing = controllers[id] { return existing }
        let made = VideoController()
        controllers[id] = made
        return made
    }

    func keep(_ ids: Set<String>) {
        for (id, controller) in controllers where !ids.contains(id) {
            controller.tearDown()
            controllers[id] = nil
        }
    }

    func removeAll() { keep([]) }
}

struct PlayerPage: View {
    @Environment(AppModel.self) private var model
    @Binding var item: FeedItem
    let isCurrent: Bool
    let video: VideoController
    @Binding var galleryZoomed: Bool
    let onItemChange: (FeedItem) -> Void
    @State private var queued = false
    /// This page started out playing from Douyin; it keeps that stream once saved.
    @State private var streamed = false
    @State private var message: String?
    @State private var hearts: [HeartBurst] = []
    @State private var captionExpanded = false
    @State private var organizing = false
    @State private var preparingShare = false
    @State private var shareFiles: ShareFiles?
    @State private var shareError: String?

    /// Width and height on record for the saved video, before the player knows them.
    private var knownVideoSize: CGSize? {
        guard let technical = item.media.first(where: \.isVideo)?.technical,
              let width = technical.width, let height = technical.height, width > 0, height > 0 else { return nil }
        return CGSize(width: width, height: height)
    }

    private var playableURL: URL? {
        guard !item.isGallery else { return nil }
        if let file = item.media.first(where: \.isVideo) { return model.client.resolve(file.url) }
        return streaming ? model.client.streamURL(item.id) : nil
    }

    /// Not on the NAS yet: the NAS relays it from Douyin while it downloads.
    private var streaming: Bool {
        !item.isGallery && !item.isSaved && !item.videoIsLost && !video.failed
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
        // Level with the back button, which sits just under the Dynamic Island.
        .overlay(alignment: .topTrailing) {
            moreMenu.padding(.top, 70).padding(.trailing, 8)
        }
    }

    @ViewBuilder
    private var content: some View {
        if let url = playableURL {
            VideoPage(video: video, url: url, poster: item.previewPath, knownSize: knownVideoSize, cookies: model.client.cookies, isCurrent: isCurrent, loadResume: loadResume, onDoubleTap: doubleTapped)
                .overlay { heartLayer }
                .overlay(alignment: .top) {
                    if isCurrent && streaming {
                        streamingChip
                    } else if isCurrent && streamed && item.isSaved {
                        savedChip
                    }
                }
                .task(id: isCurrent) {
                    guard isCurrent, streaming else { return }
                    streamed = true
                    // Opening a work that is not saved yet also saves it. "waiting" also
                    // means "no download yet", and a queued one may sit behind hours of
                    // retries: asking again moves it to the front, so only skip one that
                    // is already downloading.
                    if !queued, item.local?.state != "downloading" {
                        await save()
                    }
                    await watchDownload()
                }
                .onAppear {
                    let client = model.client
                    let itemId = item.id
                    video.onSave = { position, duration in
                        Task { try? await client.savePlayback(itemId, positionMs: position, durationMs: duration) }
                    }
                }
        } else if item.isGallery, !galleryImages.isEmpty {
            GalleryPager(images: galleryImages, zoomed: $galleryZoomed)
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

    /// Gallery stills only; a gallery's soundtrack is saved as a separate file.
    private var galleryImages: [MediaFile] {
        item.media.filter { !$0.isVideo && !($0.mimeType ?? "").hasPrefix("audio/") && $0.type != "audio" }
    }

    private var streamingChip: some View {
        Label(item.local?.state == "downloading" ? "边看边存到 NAS…" : "从抖音播放，同时存到 NAS",
              systemImage: "icloud.and.arrow.down")
            .font(.footnote.weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(.black.opacity(0.55), in: Capsule())
            .padding(.top, 60)
            .allowsHitTesting(false)
    }

    private var savedChip: some View {
        Label("已存到 NAS，下次直接从 NAS 播放", systemImage: "checkmark.icloud")
            .font(.footnote.weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(Color.green.opacity(0.55), in: Capsule())
            .padding(.top, 60)
            .allowsHitTesting(false)
    }

    /// Checks every few seconds until the streamed work lands on the NAS. The
    /// player keeps the stream it is playing, so nothing starts over.
    private func watchDownload() async {
        for _ in 0..<120 {
            try? await Task.sleep(for: .seconds(5))
            guard !Task.isCancelled else { return }
            guard let fresh = try? await model.client.item(item.id) else { continue }
            if fresh.isSaved || fresh.local?.state != item.local?.state {
                item = fresh
                onItemChange(fresh)
            }
            if fresh.isSaved {
                // The green chip says it on screen; a tap in the hand says it too.
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                return
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
        HStack(alignment: .bottom, spacing: 10) {
            caption
                .frame(maxWidth: .infinity, alignment: .leading)
            actionColumn
        }
        .foregroundStyle(.white)
        .padding(.leading, 14)
        .padding(.trailing, 8)
        .padding(.bottom, 44)
        .padding(.top, 80)
        .background(LinearGradient(colors: [.clear, .black.opacity(0.45)], startPoint: .top, endPoint: .bottom).allowsHitTesting(false))
        .sheet(isPresented: $organizing) {
            OrganizeSheet(item: $item, onItemChange: onItemChange)
        }
        .sheet(item: $shareFiles, onDismiss: { shareFiles?.cleanUp() }) { files in
            ShareSheet(items: files.urls)
                .ignoresSafeArea()
                .presentationDetents([.medium, .large])
        }
        .alert(shareError ?? "", isPresented: Binding(get: { shareError != nil }, set: { if !$0 { shareError = nil } })) {
            Button("好") {}
        }
    }

    /// Name, date, caption with bold #tags, and the soundtrack, as on Douyin.
    private var caption: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                if let creatorRoute {
                    NavigationLink(value: creatorRoute) { authorName }
                        .buttonStyle(.plain)
                        .accessibilityHint("打开博主存档主页")
                } else {
                    authorName
                }
                if let date = publishedText {
                    Text("· \(date)").font(.system(size: 13)).foregroundStyle(.white.opacity(0.7))
                }
            }
            if !item.description.isEmpty {
                Text(Self.captionText(item.description))
                    .font(.system(size: 15))
                    .lineLimit(captionExpanded ? nil : 2)
                    .onTapGesture { withAnimation(.easeOut(duration: 0.2)) { captionExpanded.toggle() } }
                    .accessibilityHint(captionExpanded ? "收起" : "展开全文")
            }
            if let organized = organizedLine {
                Button { organizing = true } label: {
                    Text(organized)
                        .font(.footnote)
                        .foregroundStyle(Theme.violet4)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                }
                .buttonStyle(.plain)
                .accessibilityHint("打开整理")
            }
            Label(musicText, systemImage: "music.note")
                .font(.system(size: 14))
                .lineLimit(1)
                .labelStyle(.titleAndIcon)
        }
        .shadow(color: .black.opacity(0.35), radius: 3, y: 1)
    }

    private var authorName: some View {
        Text("@\(item.creator?.nickname ?? item.author)")
            .font(.system(size: 17, weight: .semibold))
    }

    /// Avatar, then 精选 / 评论 / 收藏(整理) / 分享 with Douyin's own counts underneath.
    private var actionColumn: some View {
        VStack(spacing: 18) {
            if let creatorRoute {
                NavigationLink(value: creatorRoute) {
                    CreatorAvatar(path: item.creator?.avatarUrl, size: 48)
                        .overlay(Circle().strokeBorder(.white, lineWidth: 1.5))
                }
                .buttonStyle(.plain)
                .padding(.bottom, 6)
                .accessibilityLabel("打开 \(item.creator?.nickname ?? item.author) 的主页")
            }
            Button {
                Task { await toggleStar() }
            } label: {
                ActionIcon(systemName: "heart.fill", tint: item.starred == true ? Self.likeRed : .white,
                           label: countText("diggCount", fallback: "精选"))
            }
            .buttonStyle(.plain)
            .accessibilityLabel(item.starred == true ? "取消精选" : "加入精选")
            ActionIcon(systemName: "ellipsis.message.fill", tint: .white,
                       label: countText("commentCount", fallback: "评论"))
                .opacity(0.9)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("抖音评论 \(countText("commentCount", fallback: "0")) 条，评论没有存档")
            Button { organizing = true } label: {
                ActionIcon(systemName: "star.fill", tint: isOrganized ? Self.collectYellow : .white,
                           label: countText("collectCount", fallback: "收藏"))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("整理：相册、标签、备注")
            Button {
                Task { await prepareShare() }
            } label: {
                ZStack {
                    ActionIcon(systemName: "arrowshape.turn.up.right.fill", tint: .white,
                               label: countText("shareCount", fallback: "分享"))
                        .opacity(preparingShare ? 0.3 : 1)
                    if preparingShare { ProgressView().tint(.white).offset(y: -9) }
                }
            }
            .buttonStyle(.plain)
            .disabled(!item.isSaved || preparingShare)
            .opacity(item.isSaved ? 1 : 0.45)
            .accessibilityLabel(item.isSaved ? (preparingShare ? "正在从 NAS 取文件" : "分享或存到手机") : "存到 NAS 后才能分享")
        }
    }

    /// Top-right "…" for the rarer controls: speed lives here, as in Douyin's more menu.
    var moreMenu: some View {
        Menu {
            if playableURL != nil {
                Picker("播放速度", selection: Binding(get: { video.speed }, set: { video.setSpeed($0) })) {
                    ForEach(VideoController.speeds.reversed(), id: \.self) { value in
                        Text(value == 1 ? "正常" : "\(Self.speedText(value))×").tag(value)
                    }
                }
                .pickerStyle(.menu)
            }
            Button { organizing = true } label: { Label("整理", systemImage: "tag") }
        } label: {
            HStack(spacing: 4) {
                if video.speed != 1 {
                    Text("\(Self.speedText(video.speed))×").font(.system(size: 13, weight: .semibold).monospacedDigit())
                }
                Image(systemName: "ellipsis").font(.system(size: 20, weight: .bold))
            }
            .foregroundStyle(.white)
            .shadow(color: .black.opacity(0.45), radius: 4, y: 1)
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(Rectangle())
        }
        .accessibilityLabel("更多，播放速度 \(Self.speedText(video.speed)) 倍")
    }

    private static let likeRed = Color(hex: 0xFE2C55)
    private static let collectYellow = Color(hex: 0xFACE15)

    private func countText(_ key: String, fallback: String) -> String {
        guard let value = item.douyin?.statistics?[key], value > 0 else { return fallback }
        return Self.compactCount(value)
    }

    /// 9999, 1.2万, 3.4亿: how Douyin writes its counts.
    static func compactCount(_ value: Int) -> String {
        func short(_ number: Double, _ unit: String) -> String {
            let text = number >= 100 ? String(Int(number)) : String(format: "%.1f", number)
            return (text.hasSuffix(".0") ? String(text.dropLast(2)) : text) + unit
        }
        if value >= 100_000_000 { return short(Double(value) / 100_000_000, "亿") }
        if value >= 10_000 { return short(Double(value) / 10_000, "万") }
        return String(value)
    }

    /// The caption with every #tag in bold, the way Douyin sets them apart.
    static func captionText(_ text: String) -> AttributedString {
        var attributed = AttributedString(text)
        guard let pattern = try? NSRegularExpression(pattern: "#[^\\s#@]+") else { return attributed }
        let ns = text as NSString
        for match in pattern.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
            guard let range = Range(match.range, in: text),
                  let lower = AttributedString.Index(range.lowerBound, within: attributed),
                  let upper = AttributedString.Index(range.upperBound, within: attributed) else { continue }
            attributed[lower..<upper].font = .system(size: 15, weight: .semibold)
        }
        return attributed
    }

    private var musicText: String {
        let title = item.douyin?.music?.title?.trimmingCharacters(in: .whitespaces) ?? ""
        let author = item.douyin?.music?.author?.trimmingCharacters(in: .whitespaces) ?? ""
        if title.isEmpty { return "@\(item.creator?.nickname ?? item.author)创作的原声" }
        return author.isEmpty ? title : "\(title) - \(author)"
    }

    private var publishedText: String? {
        guard let published = item.publishedAt, published > 0 else { return nil }
        let date = Date(timeIntervalSince1970: TimeInterval(published))
        let calendar = Calendar.current
        let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: date), to: calendar.startOfDay(for: .now)).day ?? 0
        if days <= 0 { return "今天" }
        if days == 1 { return "昨天" }
        if days < 7 { return "\(days)天前" }
        let format = calendar.isDate(date, equalTo: .now, toGranularity: .year) ? "M月d日" : "yyyy年M月d日"
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = format
        return formatter.string(from: date)
    }

    /// Double tap anywhere on the video: a heart pops there and the work joins 精选.
    private func doubleTapped(at point: CGPoint) {
        let burst = HeartBurst(point: point, tilt: Double.random(in: -18...18))
        hearts.append(burst)
        if item.starred != true { Task { await toggleStar() } }
        Task {
            try? await Task.sleep(for: .milliseconds(900))
            hearts.removeAll { $0.id == burst.id }
        }
    }

    private var heartLayer: some View {
        ZStack {
            ForEach(hearts) { burst in
                HeartBurstView(burst: burst)
            }
        }
        .allowsHitTesting(false)
    }

    /// The saved files themselves (video, or each gallery picture), named after the work.
    private func prepareShare() async {
        let files = item.isGallery ? galleryImages : Array(item.media.filter(\.isVideo).prefix(1))
        guard !files.isEmpty else { return }
        preparingShare = true
        defer { preparingShare = false }
        let base = ShareNaming.base(author: item.creator?.nickname ?? item.author, title: item.title)
        do {
            var urls: [URL] = []
            for (index, file) in files.enumerated() {
                guard let remote = model.client.resolve(file.url) else { continue }
                let suffix = files.count > 1 ? " \(index + 1)" : ""
                let name = base + suffix + "." + ShareNaming.fileExtension(file)
                urls.append(try await model.client.downloadFile(remote, named: name))
            }
            if !urls.isEmpty { shareFiles = ShareFiles(urls: urls) }
        } catch is CancellationError {
            return
        } catch {
            model.handle(error)
            shareError = (error as? APIError)?.message ?? "取文件失败"
        }
    }

    private static func speedText(_ value: Float) -> String {
        value == value.rounded() ? String(Int(value)) : String(format: "%g", value)
    }

    private var isOrganized: Bool {
        !(item.tags ?? []).isEmpty || !(item.albums ?? []).isEmpty || !(item.note ?? "").isEmpty
    }

    /// One quiet line under the caption: tags, albums, then the note.
    private var organizedLine: String? {
        var parts: [String] = (item.tags ?? []).map { "#\($0)" }
        parts += (item.albums ?? []).map { "▣ \($0.name)" }
        if let note = item.note, !note.isEmpty { parts.append("✎ \(note)") }
        return parts.isEmpty ? nil : parts.joined(separator: "  ")
    }

    /// Only long videos are worth asking about; short clips always start over.
    private func loadResume() async -> Int? {
        if let known = item.douyin?.durationMs, Double(known) / 1000 < VideoController.resumeMinSeconds { return nil }
        return try? await model.client.playback(item.id)
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
    /// Seconds the video jumped to from a saved position; drives the "resumed" chip.
    var resumedAt: Double?
    /// Hands (position, duration) in ms to whoever keeps them on the NAS.
    var onSave: ((Int, Int) -> Void)?
    /// The video could not be loaded, e.g. Douyin would not hand an unsaved one over.
    private(set) var failed = false
    /// A frame is on screen; until then the page shows the cover instead.
    private(set) var firstFrameShown = false
    /// The video's own size once the player has read it.
    private(set) var videoSize: CGSize = .zero
    private var sizeObservation: NSKeyValueObservation?
    /// Buffer ahead while paused, for a page the owner is likely to swipe to next.
    private var wantsPreroll = false
    private var statusObservation: NSKeyValueObservation?
    private var timeObserver: Any?
    private var endObserver: NSObjectProtocol?
    private var lastSave = Date.distantPast
    /// The owner's chosen speed; shared by every video and kept across launches.
    private(set) var speed: Float = VideoController.savedSpeed
    /// Held down on the picture: plays at 2× until released, like Douyin.
    private(set) var boosting = false

    static let speeds: [Float] = [0.75, 1, 1.25, 1.5, 2]
    static let boostSpeed: Float = 2
    private static let speedKey = "playbackSpeed"
    static var savedSpeed: Float {
        let value = UserDefaults.standard.float(forKey: speedKey)
        return speeds.contains(value) ? value : 1
    }

    /// Same threshold as the server: shorter clips always start over.
    static let resumeMinSeconds: Double = 120

    func prepare(url: URL, cookies: [HTTPCookie]) {
        guard player == nil else { return }
        // AVPlayer does not read URLSession's cookie store; hand it the session.
        let asset = AVURLAsset(url: url, options: [AVURLAssetHTTPCookiesKey: cookies])
        let item = AVPlayerItem(asset: asset)
        let next = AVPlayer(playerItem: item)
        next.actionAtItemEnd = .none
        statusObservation = item.observe(\.status) { [weak self, weak next] observed, _ in
            DispatchQueue.main.async {
                guard let self else { return }
                if observed.status == .failed { self.failed = true }
                if observed.status == .readyToPlay, self.wantsPreroll, let next, next.rate == 0 {
                    self.wantsPreroll = false
                    next.preroll(atRate: self.speed)
                }
            }
        }
        sizeObservation = item.observe(\.presentationSize) { [weak self] observed, _ in
            let size = observed.presentationSize
            guard size != .zero else { return }
            DispatchQueue.main.async { self?.videoSize = size }
        }
        // play() starts at defaultRate, so a chosen speed survives pause and loop.
        next.defaultRate = speed
        endObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main
        ) { [weak self, weak next] _ in
            // Watched to the end: forget the spot, then loop like Douyin.
            self?.save(ended: true)
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
            if next.timeControlStatus == .playing, Date().timeIntervalSince(self.lastSave) >= 15 {
                self.save()
            }
        }
        player = next
    }

    /// Opens the video and starts buffering it without playing.
    func preload(url: URL, cookies: [HTTPCookie]) {
        guard player == nil else { return }
        wantsPreroll = true
        prepare(url: url, cookies: cookies)
    }

    func markFirstFrame() {
        if !firstFrameShown { firstFrameShown = true }
    }

    /// Lets go of the player, for a page the owner has scrolled far away from.
    func tearDown() {
        guard let player else { return }
        if player.timeControlStatus != .paused { save() }
        player.pause()
        if let timeObserver { player.removeTimeObserver(timeObserver) }
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }
        timeObserver = nil
        endObserver = nil
        statusObservation = nil
        sizeObservation = nil
        player.replaceCurrentItem(with: nil)
        self.player = nil
        firstFrameShown = false
        wantsPreroll = false
        paused = false
        progress = 0
    }

    func setActive(_ active: Bool, restart: Bool = false) {
        guard let player else { return }
        if active {
            // Another video may have changed the speed since this one was made.
            applySpeed(Self.savedSpeed)
            if restart { player.seek(to: .zero) }
            player.play()
            paused = false
        } else {
            if player.timeControlStatus != .paused { save() }
            player.pause()
        }
    }

    /// Continue a long video from where it was left.
    func resume(at seconds: Double) {
        guard let player else { return }
        player.seek(to: CMTime(seconds: seconds, preferredTimescale: 600))
        resumedAt = seconds
    }

    func restartFromTop() {
        player?.seek(to: .zero)
        resumedAt = nil
    }

    func save(ended: Bool = false) {
        guard let player, let item = player.currentItem else { return }
        let total = item.duration.seconds
        guard total.isFinite, total >= Self.resumeMinSeconds else { return }
        lastSave = Date()
        let position = ended ? total : player.currentTime().seconds
        onSave?(Int(position * 1000), Int(total * 1000))
    }

    func setSpeed(_ value: Float) {
        UserDefaults.standard.set(value, forKey: Self.speedKey)
        applySpeed(value)
    }

    private func applySpeed(_ value: Float) {
        speed = value
        guard let player else { return }
        player.defaultRate = value
        if player.timeControlStatus != .paused, !boosting { player.rate = value }
    }

    /// Long press: double speed while held, back to the chosen speed on release.
    func setBoosting(_ on: Bool) {
        guard let player, on != boosting else { return }
        boosting = on
        if on {
            if player.timeControlStatus == .paused { paused = false }
            player.rate = Self.boostSpeed
        } else {
            player.rate = speed
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
            save()
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
    @Environment(\.scenePhase) private var scenePhase
    let video: VideoController
    let url: URL
    /// Cover shown the instant the page opens, until the first frame replaces it.
    let poster: String?
    let knownSize: CGSize?
    let cookies: [HTTPCookie]
    let isCurrent: Bool
    /// Saved position in ms for this video, if any; nil when it should start over.
    let loadResume: () async -> Int?
    let onDoubleTap: (CGPoint) -> Void
    /// Only a load that drags on gets a spinner; a quick one shows just the cover.
    @State private var slow = false

    /// Upright videos fill the screen edge to edge, as on Douyin; wide ones sit
    /// in the middle whole.
    private var fills: Bool {
        let size = video.videoSize == .zero ? (knownSize ?? .zero) : video.videoSize
        return size.height > size.width * 1.2
    }

    var body: some View {
        ZStack {
            if let player = video.player {
                PlayerSurface(
                    player: player, video: video, fills: fills,
                    onTap: { withAnimation(.easeOut(duration: 0.15)) { video.togglePlay() } },
                    onDoubleTap: onDoubleTap,
                    onHold: { holding in withAnimation(.easeOut(duration: 0.15)) { video.setBoosting(holding) } }
                )
            }
            if !video.firstFrameShown {
                RemoteImage(path: poster, contentMode: fills ? .fill : .fit, failureIcon: "", placeholder: .black)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .clipped()
                    .allowsHitTesting(false)
                    .transition(.opacity)
                if slow {
                    ProgressView().tint(.white).controlSize(.large)
                }
            }
            if video.paused && isCurrent {
                Image(systemName: "play.fill")
                    .font(.system(size: 64))
                    .foregroundStyle(.white.opacity(0.8))
                    .shadow(color: .black.opacity(0.5), radius: 12)
                    .allowsHitTesting(false)
                    .transition(.opacity.combined(with: .scale(scale: 1.3)))
            }
            if isCurrent, let seconds = video.resumedAt {
                resumeChip(seconds)
            }
            if isCurrent && video.boosting {
                Label("2 倍速播放中", systemImage: "forward.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14).padding(.vertical, 7)
                    .background(.black.opacity(0.55), in: Capsule())
                    .frame(maxHeight: .infinity, alignment: .top)
                    .padding(.top, 110)
                    .allowsHitTesting(false)
                    .transition(.opacity)
            }
        }
        .animation(.easeOut(duration: 0.15), value: video.firstFrameShown)
        .contentShape(Rectangle())
        .accessibilityAddTraits(.isButton)
        .accessibilityLabel(video.paused ? "继续播放" : "暂停")
        .accessibilityAction { video.togglePlay() }
        .task {
            try? await Task.sleep(for: .milliseconds(800))
            slow = true
        }
        .onAppear {
            video.prepare(url: url, cookies: cookies)
            // Also resumes after coming back from the creator page.
            if isCurrent { video.setActive(true) }
        }
        .onChange(of: isCurrent) { _, current in
            // Swiping back to a short video starts it over; long ones resume below.
            video.setActive(current, restart: current)
            if !current { video.resumedAt = nil }
        }
        // Long videos pick up where they were left, on any device.
        .task(id: isCurrent) {
            guard isCurrent, let position = await loadResume() else { return }
            video.resume(at: Double(position) / 1000)
            try? await Task.sleep(for: .seconds(6))
            withAnimation { video.resumedAt = nil }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active, isCurrent { video.save() }
        }
        .onDisappear {
            video.setBoosting(false)
            video.setActive(false)
        }
    }

    private func resumeChip(_ seconds: Double) -> some View {
        HStack(spacing: 12) {
            Text("从 \(clock(seconds)) 继续播放")
                .font(.subheadline)
                .foregroundStyle(.white)
            Button("从头看") { withAnimation { video.restartFromTop() } }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 12).padding(.vertical, 5)
                .background(.white.opacity(0.18), in: Capsule())
        }
        .padding(.leading, 16).padding(.trailing, 6).padding(.vertical, 6)
        .background(.black.opacity(0.6), in: Capsule())
        .frame(maxHeight: .infinity, alignment: .bottom)
        .padding(.bottom, 150)
        .transition(.opacity)
    }

    private func clock(_ seconds: Double) -> String {
        let total = Int(seconds.rounded())
        return total >= 3600
            ? String(format: "%d:%02d:%02d", total / 3600, total / 60 % 60, total % 60)
            : String(format: "%d:%02d", total / 60, total % 60)
    }
}

/// AVPlayerLayer without AVKit's controls, so taps reach our own gesture.
private struct PlayerSurface: UIViewRepresentable {
    let player: AVPlayer
    let video: VideoController
    let fills: Bool
    let onTap: () -> Void
    let onDoubleTap: (CGPoint) -> Void
    let onHold: (Bool) -> Void

    func makeUIView(context: Context) -> PlayerLayerView {
        let view = PlayerLayerView()
        view.handlers = (onTap, onDoubleTap, onHold)
        view.playerLayer.videoGravity = fills ? .resizeAspectFill : .resizeAspect
        view.playerLayer.player = player
        view.onFirstFrame = { [weak video] in video?.markFirstFrame() }
        return view
    }

    func updateUIView(_ view: PlayerLayerView, context: Context) {
        if view.playerLayer.player !== player { view.playerLayer.player = player }
        view.handlers = (onTap, onDoubleTap, onHold)
        let gravity: AVLayerVideoGravity = fills ? .resizeAspectFill : .resizeAspect
        if view.playerLayer.videoGravity != gravity { view.playerLayer.videoGravity = gravity }
    }
}

private final class PlayerLayerView: UIView {
    override class var layerClass: AnyClass { AVPlayerLayer.self }
    var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }
    /// Called once the layer has a frame to show, so the cover can step aside.
    var onFirstFrame: (() -> Void)?
    private var readyObservation: NSKeyValueObservation?

    /// Single tap pauses, double tap hearts, press and hold plays at 2×. UIKit
    /// recognizers, unlike SwiftUI gestures here, let a swipe that starts on the
    /// video still page to the next one.
    var handlers: (tap: () -> Void, doubleTap: (CGPoint) -> Void, hold: (Bool) -> Void)?

    override init(frame: CGRect) {
        super.init(frame: frame)
        let double = UITapGestureRecognizer(target: self, action: #selector(doubleTapped(_:)))
        double.numberOfTapsRequired = 2
        let single = UITapGestureRecognizer(target: self, action: #selector(tapped))
        single.require(toFail: double)
        let hold = UILongPressGestureRecognizer(target: self, action: #selector(held(_:)))
        hold.minimumPressDuration = 0.4
        for recognizer in [double, single, hold] { addGestureRecognizer(recognizer) }
        readyObservation = playerLayer.observe(\.isReadyForDisplay, options: [.initial, .new]) { [weak self] layer, _ in
            guard layer.isReadyForDisplay else { return }
            DispatchQueue.main.async { self?.onFirstFrame?() }
        }
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    @objc private func tapped() { handlers?.tap() }

    @objc private func doubleTapped(_ recognizer: UITapGestureRecognizer) {
        handlers?.doubleTap(recognizer.location(in: self))
    }

    @objc private func held(_ recognizer: UILongPressGestureRecognizer) {
        switch recognizer.state {
        case .began: handlers?.hold(true)
        case .ended, .cancelled, .failed: handlers?.hold(false)
        default: break
        }
    }
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

/// Files fetched from the NAS for one share; removed again once the sheet closes.
struct ShareFiles: Identifiable {
    let id = UUID()
    let urls: [URL]

    func cleanUp() {
        for folder in Set(urls.map { $0.deletingLastPathComponent() }) {
            try? FileManager.default.removeItem(at: folder)
        }
    }
}

/// The system share sheet: 存储视频 / 存储图像, AirDrop, WeChat…
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}

/// File names for shared works: "博主 - 标题.mp4", safe for Files and AirDrop.
enum ShareNaming {
    static func base(author: String, title: String) -> String {
        let short = title.count > 40 ? String(title.prefix(40)) : title
        let raw = "\(author) - \(short)"
        let banned = CharacterSet(charactersIn: "/\\:*?\"<>|\n\r")
        return raw.components(separatedBy: banned).joined(separator: " ").trimmingCharacters(in: .whitespaces)
    }

    static func fileExtension(_ file: MediaFile) -> String {
        switch file.mimeType ?? "" {
        case "video/quicktime": "mov"
        case let mime where mime.hasPrefix("video/"): "mp4"
        case "image/webp": "webp"
        case "image/png": "png"
        case "image/heic": "heic"
        case let mime where mime.hasPrefix("image/"): "jpg"
        default: file.isVideo ? "mp4" : "jpg"
        }
    }
}

/// One double-tap heart: where it landed and how it leans.
struct HeartBurst: Identifiable {
    let id = UUID()
    let point: CGPoint
    let tilt: Double
}

/// Pops in large, settles, then floats up and fades, like Douyin's double-tap heart.
private struct HeartBurstView: View {
    let burst: HeartBurst
    @State private var phase = 0

    var body: some View {
        Image(systemName: "heart.fill")
            .font(.system(size: 96))
            .foregroundStyle(Color(hex: 0xFE2C55))
            .shadow(color: .black.opacity(0.25), radius: 8)
            .scaleEffect(phase == 0 ? 1.6 : phase == 1 ? 1 : 1.25)
            .opacity(phase == 2 ? 0 : 1)
            .rotationEffect(.degrees(burst.tilt))
            .position(x: burst.point.x, y: burst.point.y - (phase == 2 ? 60 : 0))
            .onAppear {
                withAnimation(.spring(response: 0.22, dampingFraction: 0.55)) { phase = 1 }
                withAnimation(.easeIn(duration: 0.35).delay(0.45)) { phase = 2 }
            }
    }
}

/// A right-column action: big glyph with a soft shadow and a count underneath.
private struct ActionIcon: View {
    let systemName: String
    let tint: Color
    let label: String

    var body: some View {
        VStack(spacing: 3) {
            Image(systemName: systemName)
                .font(.system(size: 32))
                .foregroundStyle(tint)
                .shadow(color: .black.opacity(0.3), radius: 3, y: 1)
                .frame(width: 48, height: 40)
            Text(label)
                .font(.system(size: 12, weight: .semibold).monospacedDigit())
                .foregroundStyle(.white)
                .shadow(color: .black.opacity(0.4), radius: 2, y: 1)
        }
        .contentShape(Rectangle())
    }
}
