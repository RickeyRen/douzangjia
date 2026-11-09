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
    /// Room the floating tab bar takes at the bottom of every tab.
    static let tabBarClearance: CGFloat = 62

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

    /// Keeps the last row of a scrolling page clear of the floating tab bar.
    func tabBarClearance() -> some View {
        safeAreaPadding(.bottom, Theme.tabBarClearance)
    }

    /// Dims content that scrolls under the status bar on pages without a navigation bar.
    func statusBarScrim() -> some View {
        overlay(alignment: .top) {
            Color.clear.frame(height: 0)
                .background(
                    LinearGradient(colors: [Theme.bg, Theme.bg.opacity(0.75)], startPoint: .top, endPoint: .bottom)
                        .ignoresSafeArea(edges: .top)
                )
                .allowsHitTesting(false)
        }
    }

    /// Dark list styling for Form / List screens.
    func darkList() -> some View {
        scrollContentBackground(.hidden).background(Theme.bg.ignoresSafeArea())
    }

    /// Dark system navigation bar for pushed pages and sheets.
    func darkNavigationBar() -> some View {
        toolbarBackground(Theme.bg, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
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

/// "NAS 在线" status capsule.
struct ConnectionPill: View {
    let text: String
    let color: Color

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 7, height: 7)
                .background(Circle().fill(color.opacity(0.15)).frame(width: 13, height: 13))
            Text(text).font(.system(size: 11.5, weight: .medium)).foregroundStyle(Theme.text)
        }
        .lineLimit(1)
        .fixedSize()
        .padding(.horizontal, 10)
        .frame(height: 28)
        .background(Theme.panel, in: Capsule())
        .overlay(Capsule().strokeBorder(Theme.line, lineWidth: 1))
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

/// Large page title used by the tab roots ("作品", "下载").
struct PageTitle: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 28, weight: .semibold))
            .foregroundStyle(Theme.text)
            .lineLimit(1)
    }
}

// MARK: - Buttons

/// Filled electric-violet capsule.
struct PrimaryButtonStyle: ButtonStyle {
    var compact = false
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: compact ? 13 : 15, weight: .semibold))
            .lineLimit(1)
            .foregroundStyle(.white)
            .padding(.horizontal, compact ? 16 : 20)
            .frame(minHeight: compact ? 36 : 48)
            .background(Theme.violet, in: Capsule())
            .overlay(Capsule().strokeBorder(.white.opacity(0.12), lineWidth: 1))
            .shadow(color: Theme.violet.opacity(isEnabled ? 0.45 : 0), radius: 12, y: 6)
            .opacity(isEnabled ? (configuration.isPressed ? 0.8 : 1) : 0.45)
    }
}

/// Lavender capsule used on the violet call-to-action card.
struct LavenderButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .lineLimit(1)
            .foregroundStyle(Color(hex: 0x120C33))
            .padding(.horizontal, 16)
            .frame(height: 36)
            .background(Theme.text, in: Capsule())
            .shadow(color: .black.opacity(0.25), radius: 12, y: 6)
            .opacity(isEnabled ? (configuration.isPressed ? 0.8 : 1) : 0.6)
    }
}

/// Outlined capsule: red for retry/destructive, neutral otherwise.
struct OutlineButtonStyle: ButtonStyle {
    var danger = true
    var small = false
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: small ? 11 : 12, weight: .semibold))
            .lineLimit(1)
            .fixedSize()
            .foregroundStyle(danger ? Color(hex: 0xFF8A98) : Theme.text)
            .padding(.horizontal, small ? 10 : 12)
            .frame(height: small ? 24 : 30)
            .background(danger ? Theme.red.opacity(0.06) : Theme.panel3, in: Capsule())
            .overlay(Capsule().strokeBorder(danger ? Theme.red.opacity(0.45) : Theme.line2, lineWidth: 1))
            .opacity(isEnabled ? (configuration.isPressed ? 0.7 : 1) : 0.45)
    }
}

/// Quiet bordered capsule ("暂停", "重新检查").
struct GhostButtonStyle: ButtonStyle {
    var small = true
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: small ? 12 : 13, weight: .medium))
            .lineLimit(1)
            .fixedSize()
            .foregroundStyle(small ? Theme.muted : Theme.text)
            .padding(.horizontal, small ? 11 : 16)
            .frame(height: small ? 28 : 40)
            .background(Theme.panel, in: Capsule())
            .overlay(Capsule().strokeBorder(Theme.line2, lineWidth: 1))
            .opacity(isEnabled ? (configuration.isPressed ? 0.7 : 1) : 0.45)
    }
}

// MARK: - Tab bar

struct DZTabItem: Identifiable {
    let id: Int
    let title: String
    let systemImage: String
}

/// Floating dark capsule tab bar; the selected tab is filled violet.
struct DZTabBar: View {
    @Binding var selection: Int
    let items: [DZTabItem]

    var body: some View {
        HStack(spacing: 4) {
            ForEach(items) { item in
                let on = item.id == selection
                Button {
                    selection = item.id
                } label: {
                    VStack(spacing: 2) {
                        Image(systemName: item.systemImage).font(.system(size: 17, weight: on ? .semibold : .regular))
                        Text(item.title).font(.system(size: 10.5, weight: on ? .semibold : .regular))
                    }
                    .foregroundStyle(on ? .white : Theme.muted)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background {
                        if on {
                            Capsule().fill(Theme.violet)
                                .shadow(color: Theme.violet.opacity(0.5), radius: 10, y: 4)
                        }
                    }
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(item.title)
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
        .padding(5)
        .frame(width: 276, height: 60)
        .background(.ultraThinMaterial, in: Capsule())
        .background(Color(red: 24 / 255, green: 22 / 255, blue: 31 / 255).opacity(0.86), in: Capsule())
        .overlay(Capsule().strokeBorder(Theme.line2, lineWidth: 1))
        .shadow(color: .black.opacity(0.5), radius: 15, y: 12)
        .animation(.snappy(duration: 0.25), value: selection)
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
