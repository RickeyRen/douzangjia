import SwiftUI

/// Thumbnail that resolves server-relative paths; posters on the NAS need the
/// session cookie, which the shared URLSession cookie store already carries.
struct RemoteImage: View {
    @Environment(AppModel.self) private var model
    let path: String?
    var contentMode: ContentMode = .fill

    var body: some View {
        AsyncImage(url: model.client.resolve(path), transaction: Transaction(animation: .easeOut(duration: 0.2))) { phase in
            switch phase {
            case .success(let image):
                image.resizable().aspectRatio(contentMode: contentMode)
            case .failure:
                placeholder.overlay(Image(systemName: "photo").foregroundStyle(.tertiary))
            default:
                placeholder
            }
        }
    }

    private var placeholder: some View {
        Rectangle().fill(Color(.secondarySystemBackground))
    }
}
