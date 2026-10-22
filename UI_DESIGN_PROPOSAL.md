# Sonic Telescope UI Design Proposal

**Status:** Implemented and verified against the Phase 1 acceptance checklist

**Scope:** Phase 1 local semantic library: Index → Search → Explain

**Product promise:** Find personal files by meaning while keeping the work on the user's machine.

## Design intent

Make Sonic Telescope feel like a dependable desktop instrument for finding files: focused, quiet, and transparent about what is happening. The user should understand within a few seconds where search happens, which folder is in scope, whether the local catalog is ready, and how to inspect a match before opening or moving it to Trash.

Use the operational clarity of Codex's persistent workspace and the legibility of AI Edge Gallery's local-model controls as references. Do not copy their brand assets, color systems, agent/project metaphors, or navigation. This app is a file library, so the content itself—filenames, paths, excerpts, and provenance—should carry the interface.

### Product truth to preserve

- The current supported loop is **Index → Search → Explain**.
- Indexing and semantic search use local services and a local SQLite catalog. The first model use may download model weights; explain calls Ollama at loopback and uses metadata plus a short excerpt.
- Explain is optional and can be unavailable if Ollama is not running. In-flight model calls cannot be cancelled.
- Search returns up to 20 ranked files with filename, path, excerpt, MIME type, size, score, and reasons.
- Open launches the file in its default macOS app. Trash moves the file to macOS Trash after confirmation.
- Cleanup proposals and organizer move plans are future work. The UI must not suggest that files are automatically categorized, moved, or deleted.
- Indexing and searching may overlap; their busy states and outcomes must remain independent.

## Reference takeaways

Google's AI Edge Gallery presents on-device AI as a set of focused workspaces, makes model selection and performance visible, and emphasizes local operation. Adapt the clear capability/status presentation to the catalog and explain service. The app's current behavior is narrower than Gallery's model playground, so avoid a model gallery or benchmark dashboard. [AI Edge Gallery overview](https://github.com/google-ai-edge/gallery/wiki/1.-Overview), [project README](https://github.com/google-ai-edge/gallery)

Codex's desktop direction emphasizes durable context across long-running work, a clear active workspace, and review before acting. Adapt that to folder context, background indexing progress, and a selected-file detail view. There is no need for thread lists or agent controls here. [Introducing the Codex app](https://openai.com/index/introducing-the-codex-app/)

## Information architecture

### App shell

```text
┌────────────────────┬───────────────────────────────────────────────────────┐
│ Brand              │ Top bar: Library / Semantic search · Current folder   │
│                    ├──────────────────────────────────────┬────────────────┤
│ Library            │ Search field                         │ File details   │
│                    │ Query suggestions                     │                │
│ Active folder      ├──────────────────────────────────────┤ Preview        │
│  ~/Documents       │ Result count                          │ Why this match │
│                    │ Result rows                           │ Metadata       │
│                    │                                       │ Open / Trash   │
│ Local processing   │                                       │                │
└────────────────────┴──────────────────────────────────────┴────────────────┘
```

At the default 1440 × 900 desktop viewport:

- Left rail: 232 px, fixed width, full height.
- Main canvas: flexible, 480 px minimum before details collapse.
- Detail panel: 340 px preferred, 300 px minimum; independently scrollable.
- Results canvas max width: 1100 px. On wider displays, leave intentional breathing room instead of stretching result text across the screen.
- Top bar: 56 px high. Main page gutter: 28 px. Result rows: 72–92 px depending on excerpt wrapping.

### Navigation and hierarchy

1. **Library** is the only primary destination in Phase 1. The selected folder appears in the source card and as a shortened, hover-revealed path in the sticky top bar.
2. Do not add inert Sources or Settings navigation. The current backend indexes a chosen directory but does not expose a saved-roots or preferences API.
3. Future Cleanup and Organize areas should not appear as enabled navigation. Add them only when their workflows are implemented.

### Main canvas

The default view is search-first, while making the required index setup obvious:

- Page title: **Find files by meaning**, with the Library destination and Semantic search context in the top bar.
- Root context card beneath the title: folder icon, selected path, **Choose folder**, and **Index folder**. Keep the full path available on hover/focus and show a shortened middle path visually.
- A single prominent natural-language search field follows the source card. Placeholder example: `Find the signed lease from last spring`. Search submits with Enter and a visible Search button.
- The source card shows one subtle local-processing helper: `Files and search stay on your device. First model use may download model files.` Search announces `Searching your local index` while active.
- Results area begins with a count and the exact query. Do not add unsupported filters, facets, sorting, pagination, or more-than-20 results. The server's ranking is authoritative. A sort control is future work unless the API grows an order contract.

## Key screens and states

### First run / empty catalog

- The page remains a complete workspace, not a marketing hero.
- A compact empty state says: **Start with a folder** and explains: `Choose a folder to build a searchable local catalog. Your files stay where they are.`
- Primary action: **Choose folder**. After selection, show **Index folder**.
- Search remains editable. Disable only the submit button when the query is empty; if the catalog is empty, explain the prerequisite in adjacent helper text.
- Never claim “nothing leaves your device” without the precise Ollama/Hugging Face caveat. Prefer: `Indexing and search run locally. First model use may download model files. Explain uses Ollama on this Mac.`

### Folder selected / ready

- Root card displays path and an **Index folder** primary action.
- A compact **API connected** state and indexed-file count may be sourced from `/health` or a successful index response. `/health` does not test whether Ollama is available, so never label Ollama as ready based on API health. Do not fabricate “last indexed” because the current API does not expose it.
- Keep source context visible while scrolling the result list, either in the rail or top bar.

### Indexing

- Show a persistent inline job row in the root card with stage label, determinate progress when `completed` and `total` are available, and **Cancel** while the backend accepts cancellation.
- Stage copy maps to current job data: `Scanning files…`, `Embedding 37 of 240 files`, `Saving catalog changes…`, `Cancelling…`.
- Do not show a fake percentage during scanning or saving. Do not present cancellation after writes have begun.
- On a confirmed cancellation, remove the temporary stale marker created by that indexing run because the backend guarantees no catalog changes were saved. Preserve a stale warning that was already present before the run.
- Search remains usable with its own busy indicator. If it overlaps a catalog update, preserve stale-result messaging as currently implemented.
- Completion becomes a concise summary: `Indexed 12 new · updated 4 · skipped 19 · removed 2 stale` and `Catalog total: 238`. Place file errors in a warning row with count.

### Search loading / results

- During search, disable only the Search submit control and announce `Searching your local index` via a polite live region. Leave indexing controls independent.
- Results heading: `Results` with count and query context. Use a dense list of full-width rows separated by thin rules rather than floating glass cards.
- Each row includes: file-type glyph, filename, relative/shortened path, one excerpt, optional reason text, MIME type and size in subdued metadata, and a relevance label. The current score is a similarity value; show it as `Match 0.82` (rounded to 2 decimals) or a restrained meter with numeric text. Never present it as a probability or confidence.
- Use a row container with a dedicated, keyboard-operable selection button and sibling action buttons. Do not nest Explain/Open buttons inside a clickable button. Selection opens the detail panel and has a visible selected state.
- Row quick actions: **Explain** and **Open**. **Trash** belongs in the detail panel's secondary/danger area, with confirmation. At narrow widths, row selection reveals actions rather than squeezing all controls into the row.
- Explain progress is per file: `Preparing explanation…`. Explanation calls are serialized by the backend and cannot be cancelled; disable a second Explain submission while one is active, with a clear busy state. If an explanation fails, keep the result and show an inline retry message. Do not imply the model is reading the entire document.
- If a new search replaces results, clear the detail panel when no result exists. If Trash removes the selected item, select the next row at the same index, falling back to the previous row, then clear selection if the list is empty. Announce the removed filename in a workspace-level status.

### Detail panel

Persistent on desktop after selecting a result; a slide-over panel on smaller screens.

1. Filename and file type.
2. Full path, allowed to wrap and selectable; copy-path control can be added only if implemented.
3. Existing excerpt and available metadata: MIME type, size, score/reasons.
4. **Why this match** section with Explain action and returned explanation. Before request, explain the boundary: `Generated locally by Ollama from file metadata and a short excerpt.`
5. **Open file** as the primary action. **Move to Trash…** as a visually separated destructive action. Confirmation names the file and clarifies it goes to system Trash.

If there is no preview endpoint, do not create a file preview from the path or imply the content is loaded. The existing stored excerpt is the available preview-like text.

### Zero results, stale results, and errors

- Zero results: retain the query; state `No matches in this catalog`. Suggest checking the selected folder or trying different words. Do not imply a broader filesystem search occurred.
- Stale results: show a compact amber notice above results: `The catalog changed after this search. Search again to refresh.` Keep results visible until the user searches again.
- Index errors: show warning count and preserve successful index results.
- Search/index/API error: use an inline alert near the relevant control; keep the rest of the workspace usable.
- Embedding profile conflict: explain that stored vectors cannot be compared with the current model. Offer **Clear catalog and re-index this folder** in a warning panel when no index job is active; the API returns a conflict while indexing is active. Confirmation must state that catalog rows and embeddings clear, files remain unchanged, and only the selected folder is re-indexed.
- Trash outcomes must distinguish filesystem action from catalog reconciliation. On ordinary failure, keep the row and show the reason. If the backend reports that a file reached system Trash but catalog cleanup failed, say the file was moved and the catalog may be stale; do not report a simple failure or claim the file remains. On success, remove the row and announce it was moved to Trash.
- Dismissing the macOS folder picker is a neutral no-op. Only a picker/API error should produce an error message.
- Open errors should remain associated with the selected filename and appear inline in the detail panel; avoid a modal browser alert.

## Visual system

### Direction: quiet graphite workspace

Use a neutral dark workspace with carefully limited color. The current animated aurora, translucent glass, glow, pill badges, and centered hero make a practical file utility feel more like a concept demo. Replace them with solid surfaces, crisp borders, strong type hierarchy, and small functional color signals. Do not animate ambient backgrounds.

#### Color tokens

| Token | Value | Use |
|---|---:|---|
| `canvas` | `#111315` | Main app background |
| `rail` | `#171A1D` | Navigation rail |
| `surface` | `#1C2024` | Source card, detail panel, menus |
| `surface-raised` | `#23282D` | Hovered/selected rows, input surface |
| `border` | `#30363C` | Dividers, card and control outlines |
| `text` | `#F2F4F5` | Primary text |
| `text-muted` | `#A8B0B7` | Secondary metadata |
| `text-subtle` | `#79838C` | Hints, path context |
| `accent` | `#A7D8C8` | Primary action, active nav, keyboard focus |
| `on-accent` | `#15201C` | Text/icons on accent-filled controls |
| `accent-soft` | `#C4E8DC` | Light accent text on dark controls |
| `info` | `#8EB9D8` | API/service connection and neutral progress indicators |
| `warning` | `#E5BD76` | Stale catalog, partial index warnings |
| `danger` | `#E28F8F` | Trash and errors |
| `success` | `#8CC5A5` | Completed index/action status |

Reserve accent color for active focus, primary buttons, and a small set of positive status marks. Match score must remain neutral; color should not imply certainty. Error/warning/success always include an icon or text label, never color alone.

#### Typography

- UI and body: system stack `-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`; no remote font dependency.
- Page heading: 22 px / 28 px, weight 600.
- Section heading: 14 px / 20 px, weight 600.
- Body and result filename: 13–14 px / 20 px; filename weight 550–600.
- Supporting metadata: 12 px / 16 px.
- Path: 12 px / 18 px using system monospace (`SFMono-Regular`, `Menlo`, `monospace`).
- Numeric score: tabular figures; keep numeric precision to two decimals.
- Avoid all-caps micro-labels and oversized display type.

#### Spacing, shape, and depth

- Base spacing: 4 px. Common steps: 4, 8, 12, 16, 20, 24, 32 px.
- Control height: 36 px compact, 40 px primary search and folder actions.
- Radius: 6 px controls, 8 px rows/panels, 10 px menus/dialogs. Avoid pill-shaped cards.
- Depth: surface contrast plus 1 px border. Use one soft shadow only for floating menus/dialogs; no glow and no backdrop blur.
- Icons: 16 px default, 18 px for primary actions. Use one consistent line icon set or existing icon resources; do not use emoji as file-type icons. File type glyphs should be recognizable and low contrast.

### Component specifications

| Component | Default | Hover / focus | Disabled / busy |
|---|---|---|---|
| Rail nav item | 36 px row; icon + label | Surface-raised; focus ring | Future destinations omitted or clearly disabled |
| Search input | 40 px, solid surface, 1 px border | Border accent on focus; 2 px visible ring | Search button reflects only search busy/empty-query state |
| Primary button | Accent fill, `on-accent` label, 6 px radius | Slightly brighter fill | Reduced contrast plus spinner and text; never color only |
| Secondary button | Transparent, text and border | Surface-raised | Lower contrast, no pointer |
| Result row | 8 px radius, 12 px vertical padding | Surface-raised | Selected row uses accent border/tint; no large shadow |
| Status row | Icon, sentence, optional action | No hover unless clickable | Live region semantics retained |
| Detail panel | Surface separated by border | N/A | Loading explanation does not block Open |
| Confirmation dialog | Filename and plain consequence | Focus trap; explicit cancel/action | Destructive button disabled while action runs |

All interactive elements need `:focus-visible` styling with minimum 2 px outline and 2 px offset. Hover is supplementary; selection and keyboard focus must be distinct.

## Responsive behavior

- **≥ 1360 px:** rail + results + detail panel in 3 columns (232 px rail, 480 px results, 300 px detail minimum, plus gutters).
- **780–1359 px:** rail + results; detail moves to a right-side overlay when a row is selected.
- **< 780 px:** compact top header replaces persistent rail; source selector collapses to a full-width card; detail becomes a full-height sheet. Result rows stack metadata and actions.
- **< 480 px:** use 16 px page gutters; search and source controls fill width; actions wrap into a menu or two rows. Keep path text selectable and horizontally safe—never cause page-wide overflow.
- Respect reduced-motion preference. Motion is limited to short panel transitions (150–200 ms ease-out) and progress indeterminate movement; no perpetual animation.

## Accessibility and interaction contracts

- Preserve semantic headings, button labels, input labels, `role="status"` announcements, and `role="alert"` errors.
- Search submits on Enter. Tab order follows rail → source controls → search → results → detail actions. Escape closes the detail overlay/dialog.
- Result rows must not be implemented as clickable `div`s without keyboard semantics. Use a button/select control or `tabIndex`, key handling, and appropriate selected state.
- Every icon-only button gets a descriptive accessible name. Path truncation uses visual ellipsis only; accessible text and copy selection retain the full path.
- Keep contrast at WCAG AA for body text and controls; status hues are supported by labels/icons.
- Trash and catalog reset use explicit confirmation. The reset copy must say the indexed catalog is cleared but disk files remain.
- Provide `aria-live="polite"` updates for index progress/completion and search count. Avoid announcing every high-frequency progress poll; update only when stage/count changes.

## Content and tone

- Use direct, calm verbs: **Choose folder**, **Index folder**, **Search**, **Explain**, **Open file**, **Move to Trash…**
- Explain local processing precisely and close to the relevant feature. Avoid blanket security guarantees.
- Label similarity values as matches/relevance, never confidence or probability.
- Use `folder`, `catalog`, `index`, and `search` consistently. Keep “AI” out of primary navigation and headings; name Ollama only in explanation/service details.
- Future capabilities remain absent until backed by implemented flows and API contracts.

## Implementation sequence

1. Establish the shell and tokens in `frontend/src/index.css` and `frontend/src/App.css`; remove animated aurora and glass treatments.
2. Refactor the current page into `AppShell`, `Sidebar`, `SourcePanel`, `SearchBar`, `ResultsList`, `ResultRow`, `FileDetailPanel`, and `StatusBanner` components while preserving the existing request handlers and state semantics.
3. Add selected-result state and a responsive detail panel. Keep it presentation-only for existing result data; do not invent API calls.
4. Move Explain into the detail panel and maintain per-path pending/error states. Keep Open and Trash wired to current endpoints and confirmation behavior.
5. Map existing index job stages and search/index concurrency to the visible statuses in this document.
6. Confirm responsive behavior and keyboard/screen-reader contracts in the existing browser suite after implementation. Keep this proposal separate from the product API contract.

## Acceptance checklist

- [x] The initial view communicates local file search and the selected folder without a centered marketing hero.
- [x] Folder context remains easy to find while browsing results through the sticky top bar.
- [x] Search and indexing show independent, accurate busy states.
- [x] Result rows and the detail panel expose filename, path, excerpt, MIME type, size, match value, and reasons when present.
- [x] Selecting a row reveals details and explanation without losing the result list.
- [x] Trash and catalog reset remain confirmed actions with precise consequences.
- [x] Stale results, partial index failures, cancellation, empty results, and model-profile conflicts have explicit states.
- [x] No UI implies that cleanup, organizer, auto-move, file preview, sorting, or persistent multi-root management exists today.
- [x] Keyboard focus, live announcements, and reduced motion are supported.
- [x] The interface remains usable from 320 px through wide desktop widths.

## Implementation record

The Phase 1 workspace is implemented in `frontend/src/App.jsx`, `frontend/src/App.css`, and `frontend/src/index.css`. Browser coverage lives in `frontend/e2e/app.spec.js`; 10 Playwright flows cover first run, search failures, folder-picker dismissal, search/index overlap, cancellation and saving boundaries, selection/details, Explain and Open outcomes, Trash confirmation and partial success, reset recovery, and responsive widths. Current verification: 10 browser flows pass, ESLint passes, and the production Vite build completes.

**First impression to preserve:** A calm, trustworthy private library.

## Unresolved product choices

- The question of whether a selected directory should become a persisted, multi-root source cannot be settled in the UI alone; the current API accepts one folder per index request and does not expose saved roots.
- A genuine document preview requires an API or safe local-file rendering contract. This proposal uses the stored excerpt only.
- Light theme is not specified. This proposal establishes a dark default; a light theme can be added later without changing layout or semantics.
