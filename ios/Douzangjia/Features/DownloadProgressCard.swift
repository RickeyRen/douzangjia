import SwiftUI

/// Polls the NAS for "saving to NAS" progress; one per visible screen.
@Observable
@MainActor
final class ProgressPoller {
    var progress: ArchiveProgress?
    private var task: Task<Void, Never>?

    func start(client: APIClient, onError: @escaping (Error) -> Void) {
        task?.cancel()
        task = Task { [weak self] in
            while !Task.isCancelled {
                do {
                    let next = try await client.progress()
                    self?.progress = next
                } catch {
                    onError(error)
                }
                let active = self?.progress?.active != nil
                try? await Task.sleep(for: .seconds(active ? 3 : 15))
            }
        }
    }

    func refresh(client: APIClient) async {
        if let next = try? await client.progress() { progress = next }
    }

    func stop() {
        task?.cancel()
        task = nil
    }
}

struct DownloadProgressCard: View {
    @Environment(AppModel.self) private var model
    let active: ActiveDownload
    var compact = false
    var onChanged: () async -> Void
    @State private var busy = false
    @State private var confirmStop = false

    private var label: String {
        let names = active.batches.map(\.label).joined(separator: "、")
        return names.isEmpty ? "" : "“\(names)”"
    }

    private var percent: String {
        let value = active.fraction * 100
        return value > 0 && value < 10 ? String(format: "%.1f%%", value) : "\(Int(value))%"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            totals
            if !compact && !active.current.isEmpty {
                SectionHeader(title: "正在下载", count: "\(active.current.prefix(4).count)") {
                    Text("排队 \(Format.integer(active.waitingItems))").monospacedDigit()
                }
                VStack(spacing: 0) {
                    ForEach(Array(active.current.prefix(4).enumerated()), id: \.element.id) { index, item in
                        if index > 0 { Divider().overlay(Theme.line) }
                        CurrentDownloadRow(item: item)
                    }
                }
                .card(radius: Theme.radiusInner, padding: EdgeInsets(top: 2, leading: 12, bottom: 2, trailing: 12))
            }
        }
        .alert(
            "停止下载剩下的 \(Format.integer(active.totalItems - active.completedItems - active.failedItems)) 个作品？",
            isPresented: $confirmStop
        ) {
            Button("继续下载", role: .cancel) {}
            Button("停止下载", role: .destructive) { Task { await control("cancel") } }
        } message: {
            Text("已经存好的会保留。")
        }
    }

    private var totals: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                LiveDot(color: active.isPaused ? Theme.muted : Theme.violet2)
                Text((active.isPaused ? "已暂停 " : (compact ? "正在下载 " : "")) + (label.isEmpty ? "存到 NAS" : label))
                    .font(.system(size: 12.5, weight: .medium))
                    .foregroundStyle(Theme.text)
                    .lineLimit(1)
                Spacer(minLength: 6)
                if busy { ProgressView().controlSize(.small) }
                controls
            }
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(Format.integer(active.completedItems))
                    .font(Theme.number(compact ? 22 : 26))
                    .foregroundStyle(Theme.text)
                Text("/ \(Format.integer(active.totalItems))")
                    .font(Theme.number(compact ? 13 : 14, weight: .regular))
                    .foregroundStyle(Theme.muted)
                Spacer(minLength: 6)
                Text(percent)
                    .font(Theme.number(compact ? 15 : 17))
                    .foregroundStyle(Theme.violet4)
            }
            .lineLimit(1)
            .padding(.top, compact ? 6 : 8)
            .padding(.bottom, 8)
            GlowBar(fraction: active.fraction, height: compact ? 6 : 8)
            if compact {
                HStack(spacing: 7) {
                    if let perMinute, !active.isPaused {
                        meta(perMinute)
                        dot
                    }
                    meta(active.isPaused ? "已暂停" : "预计 " + (active.etaSeconds.map { Format.eta($0) } ?? "估算中"))
                    dot
                    meta(active.isPaused ? "—" : Format.speed(active.speedBps))
                    dot
                    if perMinute == nil || active.isPaused {
                        meta("排队 \(Format.integer(active.waitingItems))")
                    }
                    if active.failedItems > 0 {
                        dot
                        meta("失败 \(Format.integer(active.failedItems))")
                    }
                    Spacer(minLength: 0)
                }
                .padding(.top, 10)
            } else {
                HStack(spacing: 0) {
                    fact("速度", active.isPaused ? "—" : Format.speed(active.speedBps))
                    if let perMinute {
                        fact("每分钟", perMinute.replacingOccurrences(of: "每分钟 ", with: ""), divider: true)
                    }
                    fact("预计剩余", active.isPaused ? "已暂停" : (active.etaSeconds.map { Format.eta($0) } ?? "估算中…"), divider: true)
                    fact("已下载", estimatedTotal, divider: true)
                }
                .padding(.top, 10)
                .overlay(alignment: .top) { Rectangle().fill(Theme.line).frame(height: 1) }
                .padding(.top, 12)
            }
        }
        .card()
        .disabled(busy)
    }

    @ViewBuilder
    private var controls: some View {
        if active.isPaused {
            Button { Task { await control("resume") } } label: {
                Label("继续", systemImage: "play.fill").labelStyle(.titleAndIcon)
            }
            .buttonStyle(GhostButtonStyle())
        } else {
            Button { Task { await control("pause") } } label: {
                Label("暂停", systemImage: "pause.fill")
            }
            .buttonStyle(GhostButtonStyle())
        }
        Button { confirmStop = true } label: {
            Image(systemName: "stop.fill").font(.system(size: 10))
        }
        .buttonStyle(GhostButtonStyle())
        .accessibilityLabel("停止")
    }

    private var perMinute: String? {
        guard let value = active.itemsPerMinute, value > 0 else { return nil }
        return value >= 10 ? "每分钟 \(Int(value.rounded())) 个" : String(format: "每分钟 %.1f 个", value)
    }

    private var dot: some View {
        Circle().fill(Theme.gray).frame(width: 3, height: 3)
    }

    private func meta(_ text: String) -> some View {
        Text(text).font(.system(size: 11.5)).foregroundStyle(Theme.muted).monospacedDigit().lineLimit(1).fixedSize()
    }

    private var estimatedTotal: String {
        let done = Format.bytes(active.downloadedBytes)
        guard let total = active.estimatedTotalBytes else { return done }
        return "\(done) / 约 \(Format.bytes(total))"
    }

    private func fact(_ title: String, _ value: String, divider: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(value).font(.system(size: 14, weight: .semibold)).monospacedDigit().foregroundStyle(Theme.text)
                .lineLimit(1).minimumScaleFactor(0.6)
            Text(title).font(.system(size: 10.5)).foregroundStyle(Theme.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.leading, divider ? 12 : 0)
        .overlay(alignment: .leading) {
            if divider { Rectangle().fill(Theme.line).frame(width: 1) }
        }
    }

    private func control(_ action: String) async {
        busy = true
        defer { busy = false }
        let targets = active.batches.filter { batch in
            switch action {
            case "resume": batch.status == "paused"
            case "pause": batch.status != "paused"
            default: true
            }
        }
        do {
            for batch in targets {
                try await model.client.controlBatch(batch.id, action: action)
            }
        } catch {
            model.handle(error)
        }
        await onChanged()
    }
}

private struct CurrentDownloadRow: View {
    let item: ArchiveProgressItem

    private var fraction: Double {
        item.totalBytes.map { Double(item.downloadedBytes) / Double(max($0, 1)) } ?? 0
    }

    var body: some View {
        HStack(spacing: 10) {
            RemoteImage(path: item.coverUrl)
                .frame(width: 32, height: 40)
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 7) {
                HStack(spacing: 8) {
                    Text(item.description.isEmpty ? "@\(item.author)" : item.description)
                        .font(.system(size: 12.5, weight: .semibold))
                        .foregroundStyle(Theme.text)
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    if item.totalBytes != nil {
                        Text("\(Int(fraction * 100))%")
                            .font(.system(size: 11, weight: .medium)).monospacedDigit()
                            .foregroundStyle(Theme.violet4)
                    }
                }
                HStack(spacing: 10) {
                    GlowBar(fraction: fraction, height: 4)
                    Text(item.totalBytes.map { "\(Format.bytes(item.downloadedBytes)) / \(Format.bytes($0))" } ?? Format.bytes(item.downloadedBytes))
                        .font(.system(size: 10.5)).monospacedDigit()
                        .foregroundStyle(Theme.muted)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .frame(width: 118, alignment: .trailing)
                }
            }
        }
        .padding(.vertical, 8)
    }
}

struct FailureSection: View {
    @Environment(AppModel.self) private var model
    let progress: ArchiveProgress
    var compact = false
    var onChanged: () async -> Void
    @State private var busy = false
    @State private var message: String?

    var body: some View {
        if compact { summary } else { list }
    }

    /// Home: one row with the count and a bulk retry.
    private var summary: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 12) {
                IconChip(systemImage: "exclamationmark.triangle")
                VStack(alignment: .leading, spacing: 1) {
                    Text("\(Format.integer(progress.failedTotal)) 个作品没能存到 NAS")
                        .font(.system(size: 13.5, weight: .semibold))
                        .foregroundStyle(Theme.text)
                        .lineLimit(1).minimumScaleFactor(0.85)
                    Text(commonReason)
                        .font(.system(size: 11.5)).foregroundStyle(Theme.muted).lineLimit(1)
                }
                Spacer(minLength: 4)
                retryButton(small: false)
            }
            if let message {
                Text(message).font(.system(size: 11.5)).foregroundStyle(Theme.muted).padding(.leading, 44)
            }
        }
        .card(padding: EdgeInsets(top: 10, leading: 14, bottom: 10, trailing: 12))
    }

    /// Downloads tab: the failed items with their reasons.
    private var list: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionHeader(title: "失败", count: Format.integer(progress.failedTotal), countColor: Theme.redText) {
                Button { Task { await retry() } } label: {
                    HStack(spacing: 4) {
                        if busy { ProgressView().controlSize(.mini) } else { Image(systemName: "arrow.clockwise").font(.system(size: 10, weight: .semibold)) }
                        Text("全部重试")
                    }
                    .foregroundStyle(Color(hex: 0xFF8A98))
                }
                .buttonStyle(.plain)
                .disabled(busy)
            }
            if let message {
                Text(message).font(.system(size: 11.5)).foregroundStyle(Theme.muted).padding(.horizontal, 2)
            }
            VStack(spacing: 0) {
                ForEach(Array(progress.failures.prefix(5).enumerated()), id: \.element.id) { index, failure in
                    if index > 0 { Divider().overlay(Theme.line) }
                    HStack(spacing: 10) {
                        IconChip(systemImage: "exclamationmark.triangle", size: 24)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(failure.description.isEmpty ? "@\(failure.author)" : failure.description)
                                .font(.system(size: 12.5, weight: .semibold))
                                .foregroundStyle(Theme.text)
                                .lineLimit(1)
                            Text("@\(failure.author)" + (Format.errorText(failure.errorCode).map { " · \($0)" } ?? ""))
                                .font(.system(size: 10.5)).foregroundStyle(Theme.muted).lineLimit(1)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 7)
                }
                if progress.failedTotal > 5 {
                    Divider().overlay(Theme.line)
                    Text("还有 \(Format.integer(progress.failedTotal - 5)) 个")
                        .font(.system(size: 11)).foregroundStyle(Theme.muted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 8)
                }
            }
            .card(radius: Theme.radiusInner, padding: EdgeInsets(top: 2, leading: 12, bottom: 2, trailing: 12))
        }
    }

    private var commonReason: String {
        progress.failures.first.flatMap { Format.errorText($0.errorCode) } ?? "稍后可以重试"
    }

    private func retryButton(small: Bool) -> some View {
        Button { Task { await retry() } } label: {
            HStack(spacing: 4) {
                if busy { ProgressView().controlSize(.mini) }
                Text("全部重试")
            }
        }
        .buttonStyle(OutlineButtonStyle(small: small))
        .disabled(busy)
    }

    private func retry() async {
        busy = true
        defer { busy = false }
        do {
            let count = try await model.client.retryFailed()
            message = "已重新加入 \(Format.integer(count)) 个作品"
        } catch {
            model.handle(error)
            message = "重试失败，请稍后再试"
        }
        await onChanged()
    }
}
