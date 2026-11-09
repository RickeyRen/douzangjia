import SwiftUI

/// "紫电数据" design tokens: near-black canvas, hairline panels, electric violet.
/// Every screen takes its colors, radii and card styling from here.
enum Theme {
    // Surfaces
    static let bg = Color(hex: 0x030203)
    static let panel = Color(hex: 0x0E0D12)
    static let panel2 = Color(hex: 0x141219)
    static let panel3 = Color(hex: 0x1C1A24)
    /// Hairline borders (lavender at 7.5% / 13%).
    static let line = Color(hex: 0xE9E4F8).opacity(0.075)
    static let line2 = Color(hex: 0xE9E4F8).opacity(0.13)

    // Brand
    static let violet = Color(hex: 0x3717F4)
    static let violet2 = Color(hex: 0x5B3BFF)
    static let violet3 = Color(hex: 0x8C76FF)
    static let violet4 = Color(hex: 0xC9BEFF)

    // Text
    static let text = Color(hex: 0xE9E4F8)
    static let muted = Color(hex: 0x8E8BA0)
    static let dim = Color(hex: 0x615F72)
    static let gray = Color(hex: 0x464657)

    // Signals
    static let lime = Color(hex: 0xC8F25A)
    static let olive = Color(hex: 0x778313)
    static let red = Color(hex: 0xFF4E64)
    static let redText = Color(hex: 0xFF7B8C)
    static let amber = Color(hex: 0xFF9F45)

    // Radii
    static let radiusCard: CGFloat = 22
    static let radiusInner: CGFloat = 18
    static let radiusTile: CGFloat = 14

    /// Horizontal page margin, as in the 390pt frames.
    static let pageInset: CGFloat = 18
    static let progressGradient = LinearGradient(colors: [violet, violet3], startPoint: .leading, endPoint: .trailing)

    /// The "save everything" call-to-action card.
    static var actionGradient: some View {
        ZStack {
            LinearGradient(
                stops: [.init(color: Color(hex: 0x4A2BFF), location: 0),
                        .init(color: violet, location: 0.45),
                        .init(color: Color(hex: 0x24109E), location: 1)],
                startPoint: .topLeading, endPoint: .bottomTrailing
            )
            RadialGradient(colors: [violet3.opacity(0.55), .clear], center: .topTrailing, startRadius: 0, endRadius: 220)
        }
    }

    static let numberFont = Font.system(.body, design: .default).monospacedDigit()

    static func number(_ size: CGFloat, weight: Font.Weight = .medium) -> Font {
        .system(size: size, weight: weight).monospacedDigit()
    }
}

extension Color {
    init(hex: UInt32, opacity: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: opacity
        )
    }

    static let brand = Theme.violet
}

// MARK: - Surfaces

struct CardModifier: ViewModifier {
    var radius: CGFloat = Theme.radiusCard
    var fill: Color = Theme.panel
    var padding: EdgeInsets? = EdgeInsets(top: 14, leading: 16, bottom: 14, trailing: 16)

    func body(content: Content) -> some View {
        content
            .padding(padding ?? EdgeInsets())
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(fill, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous).strokeBorder(Theme.line, lineWidth: 1))
    }
}

extension View {
    /// Panel with a hairline border.
    func card(radius: CGFloat = Theme.radiusCard, fill: Color = Theme.panel, padding: EdgeInsets? = EdgeInsets(top: 14, leading: 16, bottom: 14, trailing: 16)) -> some View {
        modifier(CardModifier(radius: radius, fill: fill, padding: padding))
    }

    /// Full-bleed near-black page background.
    func screenBackground() -> some View {
        background(Theme.bg.ignoresSafeArea())
    }

}

// MARK: - Small parts

/// Rounded progress track with a glowing violet fill.
struct GlowBar: View {
    let fraction: Double
    var height: CGFloat = 8
    var tint: AnyShapeStyle = AnyShapeStyle(Theme.progressGradient)

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.panel3)
                Capsule()
                    .fill(tint)
                    .frame(width: max(height, proxy.size.width * min(max(fraction, 0), 1)))
                    .shadow(color: Theme.violet2.opacity(0.7), radius: 5)
                    .opacity(fraction > 0 ? 1 : 0)
            }
        }
        .frame(height: height)
    }
}

/// Pulsing-looking dot that marks a running job.
struct LiveDot: View {
    var color: Color = Theme.violet2

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 8, height: 8)
            .background(Circle().fill(color.opacity(0.22)).frame(width: 16, height: 16))
            .shadow(color: color, radius: 5)
            .frame(width: 16, height: 16)
    }
}

enum PillStyle {
    case up, olive, down, tag, neutral

    var foreground: Color {
        switch self {
        case .up: Color(hex: 0x1A2300)
        case .olive: Color(hex: 0xF4F8D2)
        case .down: Theme.redText
        case .tag: Theme.violet4
        case .neutral: Color(hex: 0xB3B0C4)
        }
    }

    var background: Color {
        switch self {
        case .up: Theme.lime
        case .olive: Theme.olive
        case .down: Theme.red.opacity(0.16)
        case .tag: Theme.violet.opacity(0.18)
        case .neutral: Theme.muted.opacity(0.14)
        }
    }
}

struct Pill: View {
    let text: String
    var systemImage: String?
    var style: PillStyle = .up
    var large = false

    var body: some View {
        HStack(spacing: 4) {
            if let systemImage { Image(systemName: systemImage).font(.system(size: large ? 10 : 9, weight: .bold)) }
            Text(text)
        }
        .font(.system(size: large ? 12 : 11, weight: .semibold))
        .lineLimit(1)
        .fixedSize()
        .padding(.horizontal, large ? 10 : 8)
        .padding(.vertical, large ? 4 : 2.5)
        .foregroundStyle(style.foreground)
        .background(style.background, in: Capsule())
    }
}

/// "NAS 在线" status: a glowing dot and a label, sized for a toolbar item (the bar draws the glass).
struct ConnectionPill: View {
    let text: String
    let color: Color

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 7, height: 7)
                .background(Circle().fill(color.opacity(0.15)).frame(width: 13, height: 13))
            Text(text).font(.system(size: 13, weight: .medium)).foregroundStyle(Theme.text)
        }
        .lineLimit(1)
        .fixedSize()
        .padding(.horizontal, 6)
        .accessibilityElement(children: .combine)
    }
}

/// Section title row: "下载", "已在抖音消失 14 位" … "全部 ›".
struct SectionHeader<Trailing: View>: View {
    let title: String
    var count: String?
    var countColor: Color = Theme.muted
    @ViewBuilder var trailing: Trailing

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(title).font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.text)
            if let count {
                Text(count).font(.system(size: 13, weight: .medium)).monospacedDigit().foregroundStyle(countColor)
            }
            Spacer(minLength: 8)
            trailing
                .font(.system(size: 12))
                .foregroundStyle(Theme.muted)
        }
        .lineLimit(1)
        .padding(.horizontal, 2)
        .padding(.top, 14)
        .padding(.bottom, 2)
    }
}

extension SectionHeader where Trailing == EmptyView {
    init(title: String, count: String? = nil, countColor: Color = Theme.muted) {
        self.init(title: title, count: count, countColor: countColor) { EmptyView() }
    }
}

/// Small rounded square holding an icon (warning, info, failure dot).
struct IconChip: View {
    let systemImage: String
    var size: CGFloat = 32
    var tint: Color = Theme.redText
    var fill: Color = Theme.red.opacity(0.13)

    var body: some View {
        Image(systemName: systemImage)
            .font(.system(size: size * 0.42, weight: .semibold))
            .foregroundStyle(tint)
            .frame(width: size, height: size)
            .background(fill, in: RoundedRectangle(cornerRadius: size * 0.31, style: .continuous))
    }
}

/// Lets any screen switch tabs (e.g. "下载 · 全部 ›" on the home page).
private struct SelectTabKey: EnvironmentKey {
    static let defaultValue: (Int) -> Void = { _ in }
}

extension EnvironmentValues {
    var selectTab: (Int) -> Void {
        get { self[SelectTabKey.self] }
        set { self[SelectTabKey.self] = newValue }
    }
}
