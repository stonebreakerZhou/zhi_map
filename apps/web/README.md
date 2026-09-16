# 知树 Web Client

React + Vite TypeScript renders server-paged views from Python FastAPI. It contains view types only: no durable persistence, credentials, or domain transitions. `npm run dev:web` proxies API traffic to `http://127.0.0.1:8000`.

## Frontend Architecture

The default workspace is a minimal conversation view. `graph/Constellation.tsx` is mounted on demand from the top-bar graph toggle, composed around the same message viewport and single composer, so drafts, reading position and run state survive switching. `graph/gestures.ts` owns bounded pointer intent and segment/rectangle geometry; `graph/api.ts` owns contracts; `graph/Recovery.tsx` renders the fixed-screen recovery bubble and paged receipts, mounted at the shell level so removal is recoverable in both views. SVG/HTML uses existing React dependencies with no copied MindFlow implementation. One projection window is retained, and obsolete queries are debounced/cancelled. Graph selections, camera and contacts do not become model context.

Run `npm run test:gestures` for geometry and `npm run test:browser` for existing workflows plus real mouse graph interactions. Open gaps include full shell morphing, collision-aware LOD hysteresis, subtree and camera-history navigation, touch pinch, read-only policy and native desktop validation. The stable insertion-order grid is not the final constellation tree layout.

`main.tsx` mounts `components/AppShell.tsx` inside an error boundary and applies the saved theme before first paint. The shell composes `TopicNavigator`, `MessageViewport`, `Composer`, `SelectionDialog`, `ReferencesDialog`, `TopicSettings`, `TutorialOverlay` and `SettingsCenter`. Settings, account, references, context and topic management live in the lower-left account drawer; `SettingsCenter` pages through `AppearanceSettings`, `ProviderSettings`, `KnowledgeSettings` and `DataSettings`. `Dialog` uses native modal focus containment, Escape, focus restoration and asynchronous error handling. Sanitized Markdown/KaTeX (inline `$...$`/`\(...\)`, display `$$...$$`/`\[...\]`) and exact UTF-16 browser selection helpers remain isolated in `render.ts` / `selection.ts`.

`AppearanceSettings` owns the `system`/`light`/`dark` preference (persisted in `localStorage`). `KnowledgeSettings` owns a device-local document store in IndexedDB; imported files are never uploaded and are not yet injected into model context. `TutorialOverlay` renders the first-run coachmarks against real controls and is replayable from settings.

`hooks.ts` owns cancellable-effect query subscriptions. `controller.ts` owns an LRU entry-page cache (3 pages per branch, 8 total, 40 entries per page), the current branch metadata/page, serialized commands and debounced dirty drafts. Failed draft persistence prevents switching; conflicts retain drafts and refresh only the revision before retry. Run state is separate, capped at 3 concurrent runs; SSE requires started/runId/ordered seq, bounded buffers and rAF paints. Completion invalidates only affected entry caches and refreshes the active branch only if it is still the run's branch, preserving dirty drafts.

Startup uses `/api/workspace/view`, branch metadata and cursor pages. Ordinary actions and SSE completion use compact revision/affected-ID results. Normal UI flows make zero `GET /api/workspace` requests. Topic search and reference-source discovery use server-paged metadata; message/context/reference lists replace pages instead of appending. All-background selection sends a scope plus at most 200 exclusions, never all message IDs; source references retain at most 100 selections across pages. Source jumps request the anchor's page directly before restoring exact UTF-16 selection. Each list has at most 40 entries; cache limits are counts, not a byte/RSS guarantee for arbitrary-size records.

## Development Entry

Run `npm run dev:web` from the repository root and open `http://127.0.0.1:5173`. Vite proxies `/api`, `/healthz`, and `/readyz` to the FastAPI server at `http://127.0.0.1:8000`; start it with `py -m uvicorn app.main:app --app-dir backend --reload --port 8000`. Build with `npm run build`.

## User Interaction

The client lets a learner create and organize topics, send prompts, expand an exact message selection into a branch, add or remove reference snapshots, choose history references when prompted, manage titles and tags, restore a recent deletion, and export or import a workspace. Settings can configure or clear the current session's model provider.

Model settings offer protocol-aware brand presets (model names are examples, not fetched availability), custom endpoints, key visibility for the current input only, load retry, and unsaved-change protection. **Save and test** persists the current form before testing and reports save failures separately from connection failures. Changing a saved connection's protocol or endpoint requires a new key; clearing personal settings requires confirmation and reloads the environment fallback status.

New-topic clicks are guarded and reuse the current untouched empty topic. Each topic's “more” action captures that topic's ID for rename, tags, favorite and deletion. Branch deletion can be undone only before the next workspace mutation (including draft persistence), for at most ten minutes; session-mainline deletion has a separate irreversible confirmation.

The selection toolbar follows the browser range, flips below when space above is insufficient, clamps to the viewport, and hides on scroll or when the range leaves the reading viewport without clearing the native range. Pointer and keyboard selection share UTF-16 source mapping. Copy reports actual clipboard success/failure. Whole-message branching also opens a prompt preview before creating anything. Native mobile selection handles/menus remain browser-controlled.

The composer is a floating dock whose measured height reserves transcript padding, so the end of the conversation is never permanently covered. It carries the only stop control while a run is streaming.

`npm run test:browser` exercises real Chrome pointer/keyboard input, desktop (1440×900) and narrow (390×844) layouts, provider failure recovery, destructive-action guards, the bounded-history regression and the graph view. `TUTORIAL_ONLY=1` runs the onboarding suite (desktop/mobile coachmark geometry, persistence, replay); `UX_ONLY=1` and `GRAPH_ONLY=1` isolate the other suites. Screenshots are written to `test-results/`.

## Data and API Dependency

The client owns bounded pages, metadata, drafts and run state. It does not persist learning data, session credentials, or authoritative revisions in browser storage. Branch-delete undo keeps only an opaque token in memory; the server stores one bounded tombstone per owner for 10 minutes. Session-mainline deletion retains independent children and has no undo. Every workspace mutation, transfer, model setting and model request depends on FastAPI.

NDJSON downloads use the browser download manager. Uploads pass the selected `File` directly to `fetch` without `file.text()`; browser-managed buffering is implementation-dependent. The UI reports upload/validation/completion phases, not byte-level progress. The server stages incrementally. Legacy JSON import remains available below the 8 MiB request cap.
