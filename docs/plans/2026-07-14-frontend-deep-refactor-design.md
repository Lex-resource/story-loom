# Frontend Deep Refactor Design

## Product Direction

The frontend remains a focused Chinese fiction production tool rather than a generic dashboard. The existing ink-and-paper identity is retained, but the interface becomes quieter, denser, and more operational: restrained paper surfaces, clear vermilion actions, jade success states, and serif typography only where it supports reading. English labels are removed from primary navigation because they add noise without helping the workflow.

Desktop uses a compact persistent rail and a flexible work surface. Mobile uses a top application bar plus a bottom destination switcher. The writing workspace becomes a single-panel workflow on narrow screens: chapter navigation, writing stages, and the console remain reachable without forcing the editor below several screens of navigation.

## Architecture

`App.jsx` remains the composition root for this iteration, but infrastructure and chrome move out of it. Backend URL resolution and request error normalization live in `services/api.js`; page navigation and global status live in `components/shell/AppShell.jsx`; reusable feedback lives in `components/ui`. This reduces the root component's responsibility without rewriting stable generation logic.

Server data stays in the existing project store where streaming updates need shared access. Short-lived view state stays local. Requests use one JSON-aware helper with consistent errors and optional abort signals. Heavy knowledge-graph views are loaded lazily so the main writing experience does not download `vis-network` on first paint.

## Workflow And Failure Handling

Navigation is explicit and accessible, with real buttons and current-page semantics. A project selection updates both application state and URL. Backend health is represented as a state machine (`checking`, `online`, `offline`) rather than two independent booleans. User-triggered mutations surface success or failure through the existing toast channel; destructive actions stop propagation and retain confirmation.

The workspace preserves automatic stage following during generation but gives the user an obvious way to take manual control. On mobile, choosing a chapter advances to the editor panel, while a dedicated control returns to the chapter list. Loading, empty, offline, generating, paused, failed, and review-required states remain visibly distinct.

## Verification

Verification covers ESLint, Vite production build, API health, and browser checks at desktop and mobile widths. Core checks are project selection, destination navigation, workspace stage switching, project creation modal, settings access, offline feedback, and layout overflow. Existing backend tests are outside this frontend-focused change unless an API contract mismatch is discovered.
