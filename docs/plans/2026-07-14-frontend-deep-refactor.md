# Frontend Deep Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Refactor the frontend into a responsive, maintainable fiction-production workspace with consistent requests, feedback, navigation, and loading behavior.

**Architecture:** Extract application infrastructure and shell components while preserving the existing generation state machine. Introduce a small UI layer, lazy-load graph-heavy pages, and redesign responsive behavior around the core writing workflow.

**Tech Stack:** React 19, Zustand, Vite 8, Lucide React, CSS

---

### Task 1: Establish Infrastructure Boundaries

**Files:**
- Create: `frontend/src/services/api.js`
- Create: `frontend/src/hooks/useBackendHealth.js`
- Modify: `frontend/src/App.jsx`

1. Move backend URL resolution into the API module.
2. Add normalized JSON request and error handling helpers.
3. Replace the root health booleans with the health hook state machine.
4. Run `npm run lint` and `npm run build`.

### Task 2: Extract The Application Shell

**Files:**
- Create: `frontend/src/components/shell/AppShell.jsx`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/App.css`

1. Extract brand, navigation, project context, status, and responsive navigation.
2. Use semantic buttons with labels, tooltips, and current-page state.
3. Keep page content in the root composition slot.
4. Verify keyboard focus and narrow-width navigation.

### Task 3: Rebuild Shelf And Shared Feedback

**Files:**
- Create: `frontend/src/components/ui/EmptyState.jsx`
- Create: `frontend/src/components/ui/StatusBadge.jsx`
- Modify: `frontend/src/pages/ProjectShelf.jsx`
- Modify: `frontend/src/App.css`

1. Add a useful empty state and consistent status mapping.
2. Replace inline card layout styles with stable CSS classes.
3. Make project cards keyboard accessible and isolate delete actions.
4. Verify long titles, loading skeletons, and empty collections.

### Task 4: Refactor Responsive Workspace Flow

**Files:**
- Modify: `frontend/src/pages/Workspace.jsx`
- Modify: `frontend/src/components/workspace/WorkspaceSidebar.jsx`
- Modify: `frontend/src/App.css`

1. Add explicit mobile panel state for chapters versus editor.
2. Convert stage controls into a stable segmented control.
3. Reduce inline layout styles in the workspace header and guide.
4. Verify editor, outline, validator, console, and review states.

### Task 5: Reduce Initial Bundle And Normalize Page Layouts

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/pages/LivingDocs.jsx`
- Modify: `frontend/src/pages/Settings.jsx`
- Modify: `frontend/src/pages/SystemConfigs.jsx`
- Modify: `frontend/src/App.css`

1. Lazy-load secondary pages and graph-heavy views.
2. Add consistent page headers, loading fallbacks, and responsive constraints.
3. Remove mixed-language navigation and visible instructional clutter.
4. Confirm the initial bundle no longer includes `vis-network`.

### Task 6: Final Regression And Commit

**Files:**
- Modify only files required by discovered regressions.

1. Run `npm run lint`.
2. Run `npm run build`.
3. Check backend health and restart the frontend if needed.
4. Capture desktop and mobile screenshots and inspect overflow.
5. Stage all current repository changes and create one snapshot commit as requested.
