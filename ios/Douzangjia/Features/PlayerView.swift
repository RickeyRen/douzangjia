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

    var body: some View {
        ZStack(alignment: .bottom) {
            Color.black
            content
            details
        }
    }

    @ViewBuilder
    private var content: some View {
        if let video = item.media.first(where: \.isVideo), !item.isGallery {
            VideoPage(url: model.client.resolve(video.url), cookies: model.client.cookies, isCurrent: isCurrent)
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
                RemoteImage(path: item.coverUrl, contentMode: .fit).opacity(0.5)
                VStack(spacing: 14) {
                    Image(systemName: "icloud").font(.system(size: 40))
                    Text(statusText).font(.headline)
                    if item.local?.state != "downloading" {
                        Button {
                            Task { await save() }
                        } label: {
                            Label(queued ? "已加入下载" : "存到 NAS", systemImage: "icloud.and.arrow.down")
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(queued)
                    }
                    if let message { Text(message).font(.footnote).opacity(0.8) }
                }
                .foregroundStyle(.white)
            }
        }
    }

    private var statusText: String {
        switch item.local?.state {
        case "downloading": "正在存到 NAS…"
        case "retry": "下载遇到问题，稍后会自动重试"
        case "failed": "下载失败"
        default: "还没存到 NAS"
        }
    }

    private var details: some View {
        HStack(alignment: .bottom, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                Text("@\(item.author)").font(.headline)
                if !item.description.isEmpty {
                    Text(item.description).font(.subheadline).lineLimit(3)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Button {
                Task { await toggleStar() }
            } label: {
                Image(systemName: item.starred == true ? "star.fill" : "star")
                    .font(.title2)
                    .foregroundStyle(item.starred == true ? .yellow : .white)
                    .frame(width: 48, height: 48)
                    .background(.black.opacity(0.35), in: Circle())
            }
            .accessibilityLabel(item.starred == true ? "取消精选" : "加入精选")
        }
        .foregroundStyle(.white)
        .padding(.horizontal, 16)
        .padding(.bottom, 40)
        .padding(.top, 60)
        .background(LinearGradient(colors: [.clear, .black.opacity(0.7)], startPoint: .top, endPoint: .bottom))
        .allowsHitTesting(true)
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

private struct VideoPage: View {
    let url: URL?
    let cookies: [HTTPCookie]
    let isCurrent: Bool
    @State private var player: AVPlayer?
    @State private var looper: Any?

    var body: some View {
        ZStack {
            if let player {
                VideoPlayer(player: player)
            } else {
                ProgressView().tint(.white)
            }
        }
        .onAppear { prepare() }
        .onChange(of: isCurrent) { _, current in
            if current { player?.play() } else { player?.pause() }
        }
        .onDisappear {
            player?.pause()
        }
    }

    private func prepare() {
        guard player == nil, let url else { return }
        // AVPlayer does not read URLSession's cookie store; hand it the session.
        let asset = AVURLAsset(url: url, options: [AVURLAssetHTTPCookiesKey: cookies])
        let item = AVPlayerItem(asset: asset)
        let next = AVPlayer(playerItem: item)
        looper = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main
        ) { _ in
            next.seek(to: .zero)
            next.play()
        }
        player = next
        if isCurrent { next.play() }
    }
}
