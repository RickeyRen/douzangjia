import SwiftUI

/// Albums, tags and a note for one item, opened from the player.
struct OrganizeSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Binding var item: FeedItem
    let onItemChange: (FeedItem) -> Void

    @State private var albums: [Album] = []
    @State private var allTags: [TagCount] = []
    @State private var loading = true
    @State private var newTag = ""
    @State private var newAlbum = ""
    @State private var creatingAlbum = false
    @State private var note = ""
    @State private var savedNote = ""
    @State private var noteState: NoteState = .idle
    @FocusState private var focus: Field?

    private enum Field { case tag, note, album }
    private enum NoteState { case idle, saving, saved }

    private var itemTags: [String] { item.tags ?? [] }
    private var memberIds: Set<Int> { Set((item.albums ?? []).map(\.id)) }
    private var suggestions: [String] {
        let typed = newTag.trimmingCharacters(in: .whitespaces)
        return allTags.map(\.tag)
            .filter { !itemTags.contains($0) && (typed.isEmpty || $0.localizedCaseInsensitiveContains(typed)) }
            .prefix(12)
            .map { $0 }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    albumSection
                    tagSection
                    noteSection
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("整理")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
        .environment(\.colorScheme, .dark)
        .task { await load() }
        .onDisappear { Task { await saveNote() } }
    }

    // MARK: Albums

    private var albumSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            header("相册", systemImage: "rectangle.stack")
            if loading && albums.isEmpty {
                ProgressView().tint(Theme.violet3)
            } else if albums.isEmpty && !creatingAlbum {
                Text("还没有相册，建一个把喜欢的作品归到一起。")
                    .font(.footnote).foregroundStyle(Theme.muted)
            }
            FlowLayout(spacing: 8) {
                ForEach(albums) { album in
                    let inside = memberIds.contains(album.id)
                    Button { Task { await toggle(album) } } label: {
                        chipLabel(album.name, systemImage: inside ? "checkmark" : "plus", active: inside)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(inside ? "从相册 \(album.name) 移出" : "加入相册 \(album.name)")
                }
                if creatingAlbum {
                    TextField("相册名", text: $newAlbum)
                        .focused($focus, equals: .album)
                        .submitLabel(.done)
                        .onSubmit { Task { await createAlbum() } }
                        .padding(.horizontal, 14).frame(height: 36)
                        .frame(minWidth: 120)
                        .background(Theme.panel3, in: Capsule())
                        .overlay(Capsule().strokeBorder(Theme.violet3, lineWidth: 1))
                } else {
                    Button {
                        creatingAlbum = true
                        focus = .album
                    } label: {
                        chipLabel("新建相册", systemImage: "folder.badge.plus", active: false, dashed: true)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    // MARK: Tags

    private var tagSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            header("标签", systemImage: "number")
            if !itemTags.isEmpty {
                FlowLayout(spacing: 8) {
                    ForEach(itemTags, id: \.self) { tag in
                        Button { Task { await updateTags(itemTags.filter { $0 != tag }) } } label: {
                            chipLabel("#\(tag)", systemImage: "xmark", active: true, trailingIcon: true)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("去掉标签 \(tag)")
                    }
                }
            }
            HStack(spacing: 8) {
                Image(systemName: "number").foregroundStyle(Theme.dim)
                TextField("加标签，回车确认", text: $newTag)
                    .focused($focus, equals: .tag)
                    .submitLabel(.done)
                    .onSubmit { Task { await addTag(newTag, keepTyping: true) } }
            }
            .padding(.horizontal, 14).frame(height: 44)
            .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Theme.line2, lineWidth: 1))
            if !suggestions.isEmpty {
                FlowLayout(spacing: 8) {
                    ForEach(suggestions, id: \.self) { tag in
                        Button { Task { await addTag(tag) } } label: {
                            chipLabel("#\(tag)", systemImage: nil, active: false)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    // MARK: Note

    private var noteSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                header("备注", systemImage: "note.text")
                Spacer()
                switch noteState {
                case .saving: Text("保存中…").font(.caption).foregroundStyle(Theme.muted)
                case .saved: Label("已保存", systemImage: "checkmark").font(.caption).foregroundStyle(Theme.lime)
                case .idle: EmptyView()
                }
            }
            TextField("为什么收藏它、想记住什么…", text: $note, axis: .vertical)
                .focused($focus, equals: .note)
                .lineLimit(3...8)
                .padding(14)
                .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Theme.line2, lineWidth: 1))
                .onChange(of: focus) { old, new in
                    if old == .note && new != .note { Task { await saveNote() } }
                }
        }
        .padding(.bottom, 24)
    }

    // MARK: Pieces

    private func header(_ title: String, systemImage: String) -> some View {
        Label(title, systemImage: systemImage)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(Theme.text)
    }

    private func chipLabel(
        _ text: String, systemImage: String?, active: Bool, dashed: Bool = false, trailingIcon: Bool = false
    ) -> some View {
        HStack(spacing: 6) {
            if let systemImage, !trailingIcon { Image(systemName: systemImage).font(.caption.weight(.bold)) }
            Text(text).lineLimit(1)
            if let systemImage, trailingIcon { Image(systemName: systemImage).font(.caption2.weight(.bold)).opacity(0.7) }
        }
        .font(.subheadline)
        .foregroundStyle(active ? Theme.text : Theme.violet4)
        .padding(.horizontal, 14).frame(height: 36)
        .background(active ? Theme.violet.opacity(0.85) : Theme.panel3, in: Capsule())
        .overlay(
            Capsule().strokeBorder(
                active ? Theme.violet3.opacity(0.6) : Theme.line2,
                style: StrokeStyle(lineWidth: 1, dash: dashed ? [4, 3] : [])
            )
        )
        .contentShape(Capsule())
    }

    // MARK: Actions

    private func load() async {
        note = item.note ?? ""
        savedNote = note
        async let albumList = try? model.client.albums()
        async let tagList = try? model.client.tags()
        albums = await albumList ?? []
        allTags = await tagList ?? []
        loading = false
    }

    private func toggle(_ album: Album) async {
        let inside = memberIds.contains(album.id)
        let before = item.albums
        var next = item.albums ?? []
        if inside { next.removeAll { $0.id == album.id } } else { next.append(AlbumRef(id: album.id, name: album.name)) }
        item.albums = next
        do {
            try await model.client.setAlbum(album.id, contains: item.id, !inside)
            onItemChange(item)
        } catch {
            item.albums = before
            model.handle(error)
        }
    }

    private func createAlbum() async {
        let name = newAlbum.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { creatingAlbum = false; return }
        do {
            let album = try await model.client.createAlbum(name)
            albums.append(album)
            newAlbum = ""
            creatingAlbum = false
            // Creating one from here means "put this item in it".
            await toggle(album)
        } catch {
            model.handle(error)
        }
    }

    private func addTag(_ raw: String, keepTyping: Bool = false) async {
        let tag = raw.replacingOccurrences(of: "#", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
        newTag = ""
        guard !tag.isEmpty, !itemTags.contains(tag) else { return }
        await updateTags(itemTags + [tag])
        // Typing several tags in a row keeps the keyboard up; tapping a suggestion doesn't raise it.
        if keepTyping { focus = .tag }
    }

    private func updateTags(_ next: [String]) async {
        let before = item.tags
        item.tags = next
        do {
            item.tags = try await model.client.setTags(item.id, tags: next)
            onItemChange(item)
            if let fresh = try? await model.client.tags() { allTags = fresh }
        } catch {
            item.tags = before
            model.handle(error)
        }
    }

    private func saveNote() async {
        let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
        guard noteState != .saving, trimmed != savedNote.trimmingCharacters(in: .whitespacesAndNewlines) else { return }
        noteState = .saving
        do {
            let stored = try await model.client.setNote(item.id, note: trimmed)
            savedNote = stored ?? ""
            item.note = stored
            onItemChange(item)
            noteState = .saved
        } catch {
            noteState = .idle
            model.handle(error)
        }
    }
}

/// Wraps chips onto as many lines as they need.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let height = rows.map(\.height).reduce(0, +) + spacing * CGFloat(max(0, rows.count - 1))
        let width = rows.map(\.width).max() ?? 0
        return CGSize(width: proposal.width ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(width: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for index in row.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row { var indices: [Int] = []; var width: CGFloat = 0; var height: CGFloat = 0 }

    private func arrange(width: CGFloat, subviews: Subviews) -> [Row] {
        var rows: [Row] = [Row()]
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            let extra = rows[rows.count - 1].indices.isEmpty ? size.width : size.width + spacing
            if rows[rows.count - 1].width + extra > width, !rows[rows.count - 1].indices.isEmpty {
                rows.append(Row())
            }
            var row = rows[rows.count - 1]
            row.width += row.indices.isEmpty ? size.width : size.width + spacing
            row.height = max(row.height, size.height)
            row.indices.append(index)
            rows[rows.count - 1] = row
        }
        return rows.filter { !$0.indices.isEmpty }
    }
}
