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

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Image(systemName: active.isPaused ? "pause.circle.fill" : "icloud.and.arrow.down.fill")
                    .font(.title2)
                    .foregroundStyle(active.isPaused ? .orange : .blue)
                    .frame(width: 40, height: 40)
                    .background((active.isPaused ? Color.orange : Color.blue).opacity(0.15), in: RoundedRectangle(cornerRadius: 10))
                VStack(alignment: .leading, spacing: 2) {
                    Text(active.isPaused ? "已暂停存到 NAS" : "正在存到 NAS").font(.headline)
                    Text(active.batches.map(\.label).joined(separator: "、"))
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                if busy { ProgressView() }
            }

            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text("\(Int(active.fraction * 100))%")
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                    .monospacedDigit()
                Text("已完成 \(Format.integer(active.completedItems)) / \(Format.integer(active.totalItems)) 个作品")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            ProgressView(value: active.fraction)
                .tint(active.isPaused ? .orange : .blue)

            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 8) {
                GridRow {
                    fact("已下载", estimatedTotal)
                    fact("速度", active.isPaused ? "—" : Format.speed(active.speedBps))
                }
                GridRow {
                    fact("预计还要", active.isPaused ? "已暂停" : (active.etaSeconds.map { Format.eta($0) } ?? "估算中…"))
                    fact("排队 / 失败", "\(Format.integer(active.waitingItems)) / \(Format.integer(active.failedItems))")
                }
            }

            if !compact && !active.current.isEmpty {
                VStack(spacing: 8) {
                    ForEach(active.current.prefix(4)) { item in
                        CurrentDownloadRow(item: item)
                    }
                }
            }

            HStack {
                if active.isPaused {
                    Button { Task { await control("resume") } } label: {
                        Label("继续", systemImage: "play.fill").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                } else {
                    Button { Task { await control("pause") } } label: {
                        Label("暂停", systemImage: "pause.fill").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                }
                Button(role: .destructive) { confirmStop = true } label: {
                    Label("停止", systemImage: "stop.fill").frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            }
            .disabled(busy)
        }
        .padding(16)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .confirmationDialog(
            "停止下载剩下的 \(Format.integer(active.totalItems - active.completedItems - active.failedItems)) 个作品？",
            isPresented: $confirmStop,
            titleVisibility: .visible
        ) {
            Button("停止下载", role: .destructive) { Task { await control("cancel") } }
        } message: {
            Text("已经存好的会保留。")
        }
    }

    private var estimatedTotal: String {
        let done = Format.bytes(active.downloadedBytes)
        guard let total = active.estimatedTotalBytes else { return done }
        return "\(done) / 约 \(Format.bytes(total))"
    }

    private func fact(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.subheadline.weight(.semibold)).monospacedDigit()
                .lineLimit(1).minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
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

    var body: some View {
        HStack(spacing: 10) {
            RemoteImage(path: item.coverUrl)
                .frame(width: 34, height: 46)
                .clipShape(RoundedRectangle(cornerRadius: 6))
            VStack(alignment: .leading, spacing: 3) {
                Text(item.description.isEmpty ? "@\(item.author)" : item.description)
                    .font(.caption.weight(.semibold)).lineLimit(1)
                Text(item.totalBytes.map { "\(Format.bytes(item.downloadedBytes)) / \(Format.bytes($0))" } ?? Format.bytes(item.downloadedBytes))
                    .font(.caption2).foregroundStyle(.secondary).monospacedDigit()
                ProgressView(value: item.totalBytes.map { Double(item.downloadedBytes) / Double(max($0, 1)) } ?? 0)
            }
        }
    }
}

struct FailureSection: View {
    @Environment(AppModel.self) private var model
    let progress: ArchiveProgress
    var onChanged: () async -> Void
    @State private var busy = false
    @State private var message: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("\(Format.integer(progress.failedTotal)) 个作品下载失败", systemImage: "exclamationmark.circle.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.red)
                Spacer()
                Button {
                    Task { await retry() }
                } label: {
                    if busy { ProgressView() } else { Label("全部重试", systemImage: "arrow.clockwise") }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(busy)
            }
            if let message {
                Text(message).font(.caption).foregroundStyle(.secondary)
            }
            ForEach(progress.failures.prefix(5)) { failure in
                VStack(alignment: .leading, spacing: 2) {
                    Text(failure.description.isEmpty ? "@\(failure.author)" : failure.description)
                        .font(.footnote).lineLimit(1)
                    Text("@\(failure.author)" + (Format.errorText(failure.errorCode).map { " · \($0)" } ?? ""))
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
            }
        }
        .padding(16)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
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
