# iPhone 15 Pro Max Experience Design

## Objective

Make the existing 留影 archive feel complete, fast, and touch-native at the iPhone 15 Pro Max portrait viewport (`430 × 932` CSS pixels), while preserving the current desktop experience and NAS-only deployment.

## Product Direction

Use one shared React data flow and responsive presentation. Mobile gets purpose-built navigation and media controls, but it does not get a separate route or duplicate archive state. The visual language stays consistent with the current off-black interface, neutral text, single coral accent, Geist/SF/PingFang typography, and Phosphor icons.

## Mobile Information Architecture

The feed remains the default surface. A compact top bar identifies the selected collection and exposes search. A bottom navigation surface provides five reachable destinations: feed, collections, search, activity, and settings. Collections and utility destinations open as touch-sized bottom sheets; activity contains both download jobs and sync runs.

Every primary mobile action must remain visible or reachable without depending on the desktop rail. Touch targets are at least `44 × 44` CSS pixels and respect `env(safe-area-inset-top)` and `env(safe-area-inset-bottom)`.

## Feed And Pagination

The first page loads immediately. When the user approaches the final loaded card, the client requests `nextCursor`, appends unique items in stable order, and keeps the active card unchanged. Collection or search changes cancel the old result set and restart pagination from the first page. The UI exposes loading-more, end-of-archive, and recoverable load-more error states without replacing already visible media.

## Media Interaction

Vertical scrolling changes works; gallery media keeps horizontal scrolling. An active video preloads metadata, starts muted, and supports:

- tap media to play or pause;
- a dedicated sound toggle;
- visible play/pause feedback;
- a lightweight progress indicator;
- automatic pause when its card is no longer active.

Information and collection controls are real buttons. Information opens a sheet with author, description, archive date, collection membership, media state, and local-original status. Decorative actions are not presented as buttons.

## Search, Collections, And Activity

Search opens a full-width mobile search surface with an explicit label, immediate focus, clear action, loading state, empty state, and error recovery. Collection selection is available from both the top title and bottom navigation.

Activity shows download jobs and sync runs in two tabs, includes a manual full-sync action, and refreshes while visible. Status updates must not trigger feed rerenders. Settings retains session status, permanent-retention explanation, and language selection in a mobile sheet.

## Responsive And Accessibility Requirements

- Primary target: `430 × 932`, device scale factor 3, touch enabled.
- Secondary checks: `393 × 852`, `932 × 430`, and a desktop viewport at least `1440 × 1000`.
- No horizontal page overflow, clipped labels, unreachable controls, or content hidden behind safe areas.
- Sheets use dialog semantics, labelled controls, focusable close buttons, and background dismissal.
- Icon-only controls have accessible names and visible focus treatment.
- Reduced-motion preference disables smooth scrolling and non-essential transitions.
- Media text remains readable over bright imagery using a restrained bottom gradient.

## Performance Requirements

- Do not introduce a new UI dependency.
- Keep transient playback state inside each media card.
- Use deferred search and functional state updates for appended feed pages.
- Render only metadata preload for the active video; inactive videos use no preload and remain paused.
- Status polling exists only while its sheet is open and is cleaned up on close.
- Preserve `content-visibility` on feed cards and avoid scroll event listeners for vertical pagination.

## Error Handling

Initial feed errors keep the current retry screen. Pagination errors preserve existing cards and show an inline retry control. Search and utility sheets have their own local error states. Failed media remains represented by the existing waiting-for-download state and must not break scrolling.

## Verification And Acceptance

Automated component tests must prove mobile navigation reachability, pagination append/deduplication, search behavior, real media controls, information-sheet behavior, and activity refresh cleanup. Existing frontend and backend suites, lint, and production build must pass.

Rendered verification must exercise this flow at `430 × 932`: load feed, open collections, select a collection, open search, search and clear, interact with a video control, open information, open activity, and reach settings. It must also prove the twenty-item boundary loads a later page. Console errors, framework overlays, viewport clipping, and horizontal overflow are acceptance failures.

After local verification, deploy the built service to the NAS, verify the online route and current authenticated archive without exposing session material, repeat the critical iPhone viewport flow against the NAS URL, and create a local checkpoint commit. Push only if an approved private GitLab remote is configured.
