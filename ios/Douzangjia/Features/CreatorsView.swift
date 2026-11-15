import SwiftUI

struct CreatorsRoute: Hashable {}

/// 博主: everyone whose works are in the library, most collected first.
struct CreatorsView: View {
    @Environment(AppModel.self) private var model
    @State private var sort = "items"
    @State private var search = ""
    @State private var creators: [Creator] = []
    @State private var cursor: String?
    @State private var exhausted = false
    @State private var loading = false
    @State private var loadError: String?
    @State private var generation = 0

    private var query: String { search.trimmingCharacters(in: .whitespacesAndNewlines) }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 8) {
                Picker("排序", selection: $sort) {
                    Text("作品最多").tag("items")
                    Text("最近收藏").tag("recent")
                }
                .pickerStyle(.segmented)
                .padding(.top, 4)

                ForEach(Array(creators.enumerated()), id: \.element.id) { index, creator in
                    NavigationLink(value: CreatorRoute(id: creator.id)) {
                        row(creator)
                    }
                    .buttonStyle(.plain)
                    .onAppear {
                        if index >= creators.count - 10 { Task { await loadMore() } }
                    }
                }

                if loading {
                    ProgressView().frame(maxWidth: .infinity).padding(24)
                } else if let loadError, creators.isEmpty {
                    ContentUnavailableView {
                        Label("读取失败", systemImage: "wifi.exclamationmark")
                    } description: {
                        Text(loadError)
                    } actions: {
                        Button("重试") { Task { await reload() } }
                            .buttonStyle(.glassProminent)
                            .tint(Theme.violet2)
                    }
                } else if creators.isEmpty {
                    if query.isEmpty {
                        ContentUnavailableView("还没有博主", systemImage: "person.2")
                    } else {
                        ContentUnavailableView.search(text: query)
                    }
                }
            }
            .padding(.horizontal, Theme.pageInset)
            .padding(.bottom, 16)
        }
        .scrollIndicators(.hidden)
        .scrollDismissesKeyboard(.immediately)
        .screenBackground()
        .navigationTitle("博主")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $search, placement: .navigationBarDrawer(displayMode: .always), prompt: "昵称或抖音号")
        .textInputAutocapitalization(.never)
        .autocorrectionDisabled()
        .refreshable { await reload() }
        .task(id: "\(sort)|\(query)") {
            if !query.isEmpty { try? await Task.sleep(for: .milliseconds(350)) }
            if Task.isCancelled { return }
            await reload()
        }
    }

    private func row(_ creator: Creator) -> some View {
        HStack(spacing: 12) {
            CreatorAvatar(path: creator.avatarUrl, size: 44)
            VStack(alignment: .leading, spacing: 3) {
                Text(creator.nickname)
                    .font(.system(size: 14.5, weight: .semibold))
                    .foregroundStyle(Theme.text)
                    .lineLimit(1)
                HStack(spacing: 8) {
                    Text("收藏 \(Format.integer(creator.knownItemCount)) 个")
                    if creator.archivedItemCount > 0 {
                        Text("已存 \(Format.integer(creator.archivedItemCount))").foregroundStyle(Theme.lime.opacity(0.85))
                    }
                    if let unique = creator.uniqueId, !unique.isEmpty {
                        Text("@\(unique)").lineLimit(1)
                    }
                }
                .font(.system(size: 11.5))
                .foregroundStyle(Theme.muted)
                .lineLimit(1)
            }
            Spacer(minLength: 6)
            if let status = creator.archive?.status, status != .active {
                StatusBadge(status: status)
            }
            Image(systemName: "chevron.right")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Theme.dim)
        }
        .contentShape(Rectangle())
        .card(radius: Theme.radiusInner, padding: EdgeInsets(top: 10, leading: 12, bottom: 10, trailing: 14))
    }

    private func reload() async {
        generation += 1
        cursor = nil
        exhausted = false
        creators = query.isEmpty ? (model.client.cachedCreators(sort: sort)?.items ?? []) : []
        await loadMore(replacing: true)
    }

    private func loadMore(replacing: Bool = false) async {
        guard !loading, !exhausted || replacing else { return }
        loading = true
        let started = generation
        defer { loading = false }
        do {
            let page = try await model.client.creators(search: query, sort: sort, cursor: replacing ? nil : cursor)
            guard started == generation else { return }
            if replacing {
                creators = page.items
            } else {
                let known = Set(creators.map(\.id))
                creators.append(contentsOf: page.items.filter { !known.contains($0.id) })
            }
            cursor = page.nextCursor
            exhausted = page.nextCursor == nil
            loadError = nil
        } catch is CancellationError {
            return
        } catch {
            model.handle(error)
            loadError = error.localizedDescription
        }
    }
}
