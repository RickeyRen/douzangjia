import SwiftUI

/// Swipe through a gallery's images; pinch or double-tap to zoom, drag to pan.
struct GalleryPager: View {
    let images: [MediaFile]
    /// True while any image is zoomed, so the vertical feed stops paging.
    @Binding var zoomed: Bool
    @State private var page = 0

    var body: some View {
        TabView(selection: $page) {
            ForEach(Array(images.enumerated()), id: \.element.id) { index, file in
                ZoomableImage(path: file.url, zoomed: $zoomed, isCurrent: page == index)
                    .tag(index)
            }
        }
        .tabViewStyle(.page(indexDisplayMode: .never))
        .overlay(alignment: .topTrailing) {
            if images.count > 1 {
                Text("\(page + 1) / \(images.count)")
                    .font(.footnote.monospacedDigit().weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12).padding(.vertical, 6)
                    .background(.black.opacity(0.45), in: Capsule())
                    .padding(.trailing, 16)
                    // Level with the player's close button (40pt, 8pt below the safe area).
                    .padding(.top, Self.topInset + 14)
                    .accessibilityLabel("第 \(page + 1) 张，共 \(images.count) 张")
                    .allowsHitTesting(false)
            }
        }
        // Keep the swipe between images while zoomed in out of the way.
        .onChange(of: page) { _, _ in zoomed = false }
    }

    /// The player ignores the safe area, so read the notch inset from the window.
    private static var topInset: CGFloat {
        let scene = UIApplication.shared.connectedScenes.first { $0 is UIWindowScene } as? UIWindowScene
        return scene?.windows.first?.safeAreaInsets.top ?? 0
    }
}

private struct ZoomableImage: View {
    let path: String
    @Binding var zoomed: Bool
    let isCurrent: Bool
    @State private var scale: CGFloat = 1
    @State private var baseScale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var baseOffset: CGSize = .zero

    private static let maxScale: CGFloat = 5
    private static let doubleTapScale: CGFloat = 2.5

    var body: some View {
        GeometryReader { proxy in
            RemoteImage(path: path, contentMode: .fit, failureIcon: "photo")
                .frame(width: proxy.size.width, height: proxy.size.height)
                .scaleEffect(scale)
                .offset(offset)
                .contentShape(Rectangle())
                .gesture(magnify(in: proxy.size))
                // Panning only takes over the swipe once the image is zoomed.
                .simultaneousGesture(scale > 1 ? pan(in: proxy.size) : nil)
                .onTapGesture(count: 2) { location in toggleZoom(at: location, in: proxy.size) }
        }
        .clipped()
        .onChange(of: isCurrent) { _, current in if !current { reset(animated: false) } }
        .accessibilityElement()
        .accessibilityLabel("图片")
        .accessibilityHint("双击放大或还原")
        .accessibilityAddTraits(.isImage)
    }

    private func magnify(in size: CGSize) -> some Gesture {
        MagnifyGesture()
            .onChanged { value in
                scale = min(Self.maxScale, max(0.8, baseScale * value.magnification))
                zoomed = scale > 1.01
            }
            .onEnded { _ in
                if scale <= 1.01 {
                    reset(animated: true)
                } else {
                    baseScale = scale
                    offset = clamped(offset, in: size)
                    baseOffset = offset
                }
            }
    }

    private func pan(in size: CGSize) -> some Gesture {
        // A few points of slack so a double-tap is never read as a drag.
        DragGesture(minimumDistance: 4)
            .onChanged { value in
                offset = clamped(
                    CGSize(width: baseOffset.width + value.translation.width,
                           height: baseOffset.height + value.translation.height),
                    in: size
                )
            }
            .onEnded { _ in baseOffset = offset }
    }

    private func toggleZoom(at location: CGPoint, in size: CGSize) {
        withAnimation(.spring(duration: 0.3)) {
            if scale > 1.01 {
                reset(animated: false)
            } else {
                // Zoom toward the tapped point, as Photos does.
                let target = Self.doubleTapScale
                scale = target
                baseScale = target
                let dx = (size.width / 2 - location.x) * (target - 1)
                let dy = (size.height / 2 - location.y) * (target - 1)
                offset = clamped(CGSize(width: dx, height: dy), in: size)
                baseOffset = offset
                zoomed = true
            }
        }
    }

    /// Never let the image slide further than its zoomed edges.
    private func clamped(_ proposed: CGSize, in size: CGSize) -> CGSize {
        let limitX = size.width * (scale - 1) / 2
        let limitY = size.height * (scale - 1) / 2
        return CGSize(width: min(limitX, max(-limitX, proposed.width)),
                      height: min(limitY, max(-limitY, proposed.height)))
    }

    private func reset(animated: Bool) {
        let apply = {
            scale = 1
            baseScale = 1
            offset = .zero
            baseOffset = .zero
        }
        if animated { withAnimation(.spring(duration: 0.3), apply) } else { apply() }
        zoomed = false
    }
}
