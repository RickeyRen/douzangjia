import SwiftUI

struct ReviewRoute: Hashable {}

/// 收藏回顾: what the owner collected month by month, what vanished, whom they love.
/// The NAS builds it once a day; the first visit waits for the first snapshot.
struct ReviewView: View {
    @Environment(AppModel.self) private var model
    @State private var review: CollectionReview?
    @State private var building = false
    @State private var loadError: String?

    private static let pollSeconds: UInt64 = 10

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                if let review {
                    summary(review)
                    months(review)
                    vanished(review.vanished)
                    if !review.topCreators.isEmpty { creators(review.topCreators) }
                    if !review.publishedYears.isEmpty { years(review.publishedYears) }
                } else if let loadError {
                    ContentUnavailableView {
                        Label("读取失败", systemImage: "wifi.exclamationmark")
                    } description: {
                        Text(loadError)
                    } actions: {
                        Button("重试") { Task { await load() } }
                            .buttonStyle(.glassProminent)
                            .tint(Theme.violet2)
                    }
                    .card()
                } else {
                    VStack(spacing: 10) {
                        ProgressView().tint(Theme.violet3)
                        Text(building ? "第一次生成要一分钟左右，好了会自动显示。" : "正在读取…")
                            .font(.system(size: 13))
                            .foregroundStyle(Theme.muted)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 60)
                }
            }
            .padding(.horizontal, Theme.pageInset)
            .padding(.bottom, 16)
        }
        .scrollIndicators(.hidden)
        .screenBackground()
        .navigationTitle("收藏回顾")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await poll() }
    }

    // MARK: Sections

    private func summary(_ review: CollectionReview) -> some View {
        let totals = review.totals
        let share = totals.items > 0 ? Int((Double(totals.saved) / Double(totals.items) * 100).rounded()) : 0
        return VStack(alignment: .leading, spacing: 10) {
            if let since = totals.since {
                let date = Calendar(identifier: .gregorian).dateComponents(in: .shanghai, from: Date(timeIntervalSince1970: Double(since)))
                Text("从 \(String(date.year ?? 0)) 年 \(date.month ?? 0) 月开始，你一共收藏了")
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.muted)
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(Format.integer(totals.items)).font(Theme.number(34)).foregroundStyle(Theme.text)
                    Text("个作品").font(.system(size: 14)).foregroundStyle(Theme.muted)
                }
                .lineLimit(1).minimumScaleFactor(0.6)
                (Text(Format.integer(totals.saved)).foregroundColor(Theme.lime).monospacedDigit()
                 + Text(" 个已经存到 NAS（\(share)%）"))
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(Theme.text)
                GeometryReader { proxy in
                    Capsule().fill(Theme.panel3)
                        .overlay(alignment: .leading) {
                            Capsule().fill(Theme.progressGradient)
                                .frame(width: max(6, proxy.size.width * Double(share) / 100))
                        }
                }
                .frame(height: 6)
            } else {
                Text("还没有收藏记录。").font(.system(size: 14)).foregroundStyle(Theme.muted)
            }
            Text("每天更新一次 · \(Format.relative(review.builtAt))")
                .font(.system(size: 11))
                .foregroundStyle(Theme.dim)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .card()
    }

    private func months(_ review: CollectionReview) -> some View {
        let peak = max(1, review.months.map(\.added).max() ?? 1)
        return VStack(alignment: .leading, spacing: 0) {
            SectionHeader(title: "每月新收藏")
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 12) {
                    legend(color: Theme.violet2, label: "已存到 NAS")
                    legend(color: Theme.violet.opacity(0.35), label: "还没存")
                }
                ForEach(review.months) { entry in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text(monthLabel(entry.month))
                                .font(.system(size: 12.5, weight: .medium))
                                .foregroundStyle(Theme.text)
                            if entry.month == review.firstMonth {
                                Text("首次导入")
                                    .font(.system(size: 10.5, weight: .semibold))
                                    .foregroundStyle(Theme.violet4)
                                    .padding(.horizontal, 6).padding(.vertical, 1.5)
                                    .background(Capsule().fill(Theme.violet.opacity(0.28)))
                            }
                            Spacer(minLength: 6)
                            Text(Format.integer(entry.added))
                                .font(.system(size: 12.5, weight: .semibold))
                                .monospacedDigit()
                                .foregroundStyle(Theme.text)
                        }
                        .lineLimit(1)
                        GeometryReader { proxy in
                            let width = max(4, proxy.size.width * Double(entry.added) / Double(peak))
                            let savedShare = entry.added > 0 ? Double(entry.saved) / Double(entry.added) : 0
                            ZStack(alignment: .leading) {
                                Capsule().fill(Theme.violet.opacity(0.35)).frame(width: width)
                                Capsule().fill(Theme.violet2).frame(width: width * savedShare)
                            }
                        }
                        .frame(height: 8)
                    }
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(monthLabel(entry.month))新收藏 \(entry.added) 个，已存 \(entry.saved) 个")
                }
                if review.firstMonth != nil {
                    Text("抖藏家开始工作之前的收藏，都算在首次导入的那个月。")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.dim)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .card()
        }
    }

    private func vanished(_ vanished: CollectionReview.Vanished) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionHeader(title: "已经消失的作品")
            VStack(alignment: .leading, spacing: 8) {
                Text("抖音上已删除或设为私密").font(.system(size: 12)).foregroundStyle(Theme.muted)
                Text(Format.integer(vanished.total)).font(Theme.number(30)).foregroundStyle(Theme.text)
                HStack(spacing: 14) {
                    Label("幸好存下了 \(Format.integer(vanished.saved)) 个", systemImage: "checkmark.shield.fill")
                        .foregroundStyle(Theme.lime)
                    if vanished.lost > 0 {
                        Label("没来得及存 \(Format.integer(vanished.lost)) 个", systemImage: "icloud.slash")
                            .foregroundStyle(Theme.redText)
                    }
                }
                .font(.system(size: 12.5, weight: .medium))
                .lineLimit(1).minimumScaleFactor(0.8)
                if vanished.total > 0 {
                    NavigationLink(value: GoneWorksRoute()) {
                        HStack(spacing: 3) {
                            Text("去看看")
                            Image(systemName: "chevron.right").font(.system(size: 10, weight: .semibold))
                        }
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Theme.violet4)
                        .padding(.top, 2)
                    }
                    .buttonStyle(.plain)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .card()
        }
    }

    private func creators(_ creators: [CollectionReview.TopCreator]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionHeader(title: "最爱的博主", count: "前 \(creators.count) 位")
            VStack(spacing: 0) {
                ForEach(Array(creators.enumerated()), id: \.element.id) { index, creator in
                    NavigationLink(value: CreatorRoute(id: creator.id)) {
                        HStack(spacing: 10) {
                            Text("\(index + 1)")
                                .font(.system(size: 13, weight: .semibold))
                                .monospacedDigit()
                                .foregroundStyle(index < 3 ? Theme.violet4 : Theme.dim)
                                .frame(width: 20)
                            CreatorAvatar(path: creator.avatarUrl, size: 34)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(creator.name)
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundStyle(Theme.text)
                                    .lineLimit(1)
                                if creator.vanished > 0 {
                                    Text("\(creator.vanished) 个已消失")
                                        .font(.system(size: 11))
                                        .foregroundStyle(Theme.redText)
                                }
                            }
                            Spacer(minLength: 6)
                            Text("\(Format.integer(creator.count)) 个")
                                .font(.system(size: 13))
                                .monospacedDigit()
                                .foregroundStyle(Theme.muted)
                            Image(systemName: "chevron.right")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(Theme.dim)
                        }
                        .padding(.vertical, 8)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    if index < creators.count - 1 {
                        Divider().overlay(Theme.line).padding(.leading, 64)
                    }
                }
            }
            .card(padding: EdgeInsets(top: 6, leading: 12, bottom: 6, trailing: 14))
        }
    }

    private func years(_ years: [CollectionReview.Year]) -> some View {
        let peak = max(1, years.map(\.count).max() ?? 1)
        return VStack(alignment: .leading, spacing: 0) {
            SectionHeader(title: "收藏的作品发布于")
            VStack(alignment: .leading, spacing: 10) {
                Text("按作品在抖音上的发布年份").font(.system(size: 12)).foregroundStyle(Theme.muted)
                HStack(alignment: .bottom, spacing: 6) {
                    ForEach(years) { entry in
                        VStack(spacing: 4) {
                            Text(Format.compact(entry.count))
                                .font(.system(size: 10.5, weight: .medium))
                                .monospacedDigit()
                                .foregroundStyle(Theme.muted)
                                .lineLimit(1).minimumScaleFactor(0.7)
                            RoundedRectangle(cornerRadius: 4, style: .continuous)
                                .fill(Theme.progressGradient)
                                .frame(height: max(3, 110 * Double(entry.count) / Double(peak)))
                            Text(entry.year)
                                .font(.system(size: 10.5))
                                .monospacedDigit()
                                .foregroundStyle(Theme.muted)
                                .lineLimit(1).minimumScaleFactor(0.7)
                        }
                        // A lone year should read as a column, not a slab.
                        .frame(maxWidth: 44)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel("\(entry.year) 年发布：\(entry.count) 个")
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 150, maxHeight: 150, alignment: .bottom)
            }
            .card()
        }
    }

    private func legend(color: Color, label: String) -> some View {
        HStack(spacing: 5) {
            RoundedRectangle(cornerRadius: 2.5).fill(color).frame(width: 8, height: 8)
            Text(label)
        }
        .font(.system(size: 11))
        .foregroundStyle(Theme.muted)
    }

    private func monthLabel(_ month: String) -> String {
        let parts = month.split(separator: "-")
        guard parts.count == 2, let number = Int(parts[1]) else { return month }
        return "\(parts[0]) 年 \(number) 月"
    }

    // MARK: Loading

    /// Polls while the NAS is still building the first snapshot.
    private func poll() async {
        if review == nil { review = model.client.cachedReview() }
        while !Task.isCancelled {
            await load()
            guard building else { return }
            try? await Task.sleep(nanoseconds: Self.pollSeconds * 1_000_000_000)
        }
    }

    private func load() async {
        do {
            switch try await model.client.review() {
            case .building:
                building = true
            case .ready(let fresh):
                building = false
                review = fresh
            }
            loadError = nil
        } catch is CancellationError {
            return
        } catch {
            model.handle(error)
            if review == nil { loadError = error.localizedDescription }
        }
    }
}

private extension TimeZone {
    static let shanghai = TimeZone(identifier: "Asia/Shanghai")!
}
