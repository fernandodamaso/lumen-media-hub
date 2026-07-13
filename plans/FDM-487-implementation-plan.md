# FDM-487 Implementation Plan

## Goal

Ship an **Automation** dashboard board so a visitor can tell at a glance whether media automations are healthy and what to do next — without reading raw logs or changing configuration.

Linear: [FDM-487](https://linear.app/fdamaso/issue/FDM-487/understand-automation-health-at-a-glance)

**Outcome:** service health, preview/upcoming work, actionable problems, and a generated timestamp appear as flat status-led tiles with deliberate loading / empty / partial / failure handling.

## Current state

| Area | State |
|------|--------|
| Port | `projects/dashboard/src/app/downloads/media-stack-api.ts` — torrents + calendar + Arr library only |
| Mock | `projects/dashboard/src/app/downloads/mock-media-stack-api.ts` — no automation summary |
| Dashboard home | `DashboardPage` in `app.routes.ts` composes `<mm-calendar-board />` + `<mm-downloads-board />` with facade providers |
| Automation UI | **Missing** — no `automation/` folder, no sidebar route (correct: this ticket is a board, not a nav destination) |
| Live HTTP adapter | Out of scope (FDM-492) |
| Reports / cron history | Out of scope (FDM-488) |

**Reference patterns to copy:**

- Downloads: `downloads.facade.ts` → `downloads-board.ts` → `downloads-format.ts` + specs
- Calendar: same slice shape; imports port from `../downloads/media-stack-api`
- Board wiring: facade in `DashboardPage.providers`, board starts polling in constructor
- UI: `MmStateCard` / `MmStatus` / `MmButton` from `media-ui`; styles use `--mm-component-*` tokens only

## Approach (port → mock → facade → board → wiring)

Follow the established vertical slice. Keep all automation port types and normalizers in the shared boundary file; keep the feature UI under a new `automation/` folder.

```
media-stack-api.ts          ← add DTO + domain + normalizeAutomationSummary + port method
mock-media-stack-api.ts     ← deterministic healthy / partial / empty / fail scenarios
automation/
  automation.facade.ts      ← signals + status machine + refresh/poll
  automation-format.ts      ← label/tone maps (semantic text + MmStatus tone)
  automation-board.ts       ← flat tiles UI
  *.spec.ts                 ← normalizer coverage lives in media-stack-api.spec.ts
app.routes.ts               ← import board + AutomationFacade on DashboardPage
```

### Domain model (port boundary)

Add these types to `media-stack-api.ts` (names may be adjusted only if a live `homepage-actions` field map is confirmed later; do **not** invent HTTP paths here).

**Raw DTO** (vendor/backend-shaped; stays behind the boundary):

```typescript
export type MediaStackAutomationServiceStatusDto =
  | 'healthy'
  | 'degraded'
  | 'down'
  | 'unknown';

export interface MediaStackAutomationServiceDto {
  id: string;
  name: string;
  status: string; // normalize to MediaStackAutomationServiceStatusDto
  detail?: string;
}

export interface MediaStackAutomationPreviewItemDto {
  id: string;
  title: string;
  when?: string;
  kind?: string;
}

export interface MediaStackAutomationProblemDto {
  id: string;
  summary: string;
  serviceId?: string;
  severity?: string; // normalize to 'actionable' | 'warning' | 'info'
}

export interface MediaStackAutomationSummaryDto {
  generatedAt: string; // ISO-8601
  services?: MediaStackAutomationServiceDto[] | null;
  preview?: MediaStackAutomationPreviewItemDto[] | null;
  problems?: MediaStackAutomationProblemDto[] | null;
  /** When a section was intentionally omitted by the backend */
  unavailable?: {
    services?: boolean;
    preview?: boolean;
    problems?: boolean;
  };
}
```

**Domain view-models** (UI-safe):

```typescript
export type AutomationServiceStatus = 'healthy' | 'degraded' | 'down' | 'unknown';
export type AutomationProblemSeverity = 'actionable' | 'warning' | 'info';

export interface AutomationService {
  id: string;
  name: string;
  status: AutomationServiceStatus;
  detail: string;
}

export interface AutomationPreviewItem {
  id: string;
  title: string;
  when: string;
  kind: string;
}

export interface AutomationProblem {
  id: string;
  summary: string;
  serviceId: string | null;
  severity: AutomationProblemSeverity;
}

export interface AutomationSectionAvailability {
  services: 'present' | 'empty' | 'unavailable';
  preview: 'present' | 'empty' | 'unavailable';
  problems: 'present' | 'empty' | 'unavailable';
}

export interface AutomationSummary {
  generatedAt: string;
  services: AutomationService[];
  preview: AutomationPreviewItem[];
  problems: AutomationProblem[];
  availability: AutomationSectionAvailability;
}
```

**Port method (additive only):**

```typescript
getAutomationSummary(): Promise<MediaStackAutomationSummaryDto>;
```

**Normalizer:** `normalizeAutomationSummary(dto)` — clamp unknown statuses to `'unknown'`, default missing strings, derive `availability` from null/`unavailable` flags vs empty arrays, never throw on partial payloads.

**Priority helper (pure, tested):** `summarizeAutomationHealth(summary)` → `{ overall: AutomationServiceStatus; actionableCount: number }` so the facade/board can sort unhealthy services first and keep healthy noise calm.

### Facade state machine

`AutomationStatus = 'loading' | 'ready' | 'empty' | 'partial' | 'error'`

| Status | When |
|--------|------|
| `loading` | Initial; until first successful or failed refresh |
| `ready` | Summary returned; all three sections `present` or `empty` with at least one useful signal (any service, preview item, or problem) |
| `empty` | Successful response with no services, no preview, no problems, and no section marked unavailable |
| `partial` | Successful response where at least one section is `unavailable`, **or** mixed present/unavailable — board must still render what exists |
| `error` | Promise rejection / thrown error |

Signals (mirror downloads/calendar): `_status`, `_summary`, `_error` with `.asReadonly()`. Polling via `startPolling` (default ~60s like calendar) + `DestroyRef` cleanup. No mutation actions in v1.

### Board UI

Flat status-led tiles (not a card-heavy dashboard):

1. **Section heading** — eyebrow “Operations”, title “Automation”, short copy; show generated timestamp when ready/partial.
2. **Loading** — `mm-state-card` “Checking automations…”.
3. **Error** — `mm-state-card` danger + Retry → `facade.refresh()`.
4. **Empty** — calm empty state: “No automation data yet”.
5. **Ready / partial** — three tile regions:
   - **Services** — list/tiles with `mm-status` label + tone from `AUTOMATION_SERVICE_STATUS_VIEW`; unhealthy (`down`/`degraded`) listed before healthy; healthy uses quiet success/info copy, not alert styling that competes with failures.
   - **Preview** — upcoming work lines; if `unavailable`, show explicit “Preview unavailable” copy (not a blank hole); if `empty`, “Nothing upcoming”.
   - **Problems** — actionable items first (`severity === 'actionable'`); use danger/warning tones with text labels. If none and available, calm “No open problems”.
6. Partial banner: when status is `partial`, a single polite `role="status"` line naming which sections are unavailable.

Semantic status is **label text via `MmStatus`**, not color alone. No configure/restart/edit buttons.

### Wiring

Update `DashboardPage` in `app.routes.ts`:

- `imports: [CalendarBoard, DownloadsBoard, AutomationBoard]`
- `providers: [CalendarFacade, DownloadsFacade, AutomationFacade]`
- Template: place `<mm-automation-board />` near downloads (operations cluster). Exact asymmetric layout is FDM-491; for this ticket a sequential section under/above downloads is enough so the board is visible and independently stateful.

Do **not** add a sidebar nav item or `/automation` route.

## File-by-file changes (concrete paths)

| Path | Action |
|------|--------|
| `projects/dashboard/src/app/downloads/media-stack-api.ts` | Add automation DTO/domain types; `getAutomationSummary()` on `MediaStackApi`; export `normalizeAutomationSummary`, `summarizeAutomationHealth` |
| `projects/dashboard/src/app/downloads/media-stack-api.spec.ts` | Tests for normalizer edge cases (unknown status, null sections, unavailable flags, empty arrays) and health summary ordering/counts |
| `projects/dashboard/src/app/downloads/mock-media-stack-api.ts` | Implement `getAutomationSummary()` with default mixed-healthy demo payload; optional internal scenario switch for specs |
| `projects/dashboard/src/app/downloads/mock-media-stack-api.spec.ts` | Assert default demo shape; scenario helpers if exposed |
| `projects/dashboard/src/app/automation/automation.facade.ts` | **Create** — inject `MEDIA_STACK_API`, status machine, polling, refresh |
| `projects/dashboard/src/app/automation/automation.facade.spec.ts` | **Create** — loading→ready/empty/partial/error; polling start-once; destroy stops timer |
| `projects/dashboard/src/app/automation/automation-format.ts` | **Create** — `AUTOMATION_SERVICE_STATUS_VIEW`, `AUTOMATION_PROBLEM_SEVERITY_VIEW`, `formatGeneratedAt` |
| `projects/dashboard/src/app/automation/automation-format.spec.ts` | **Create** — every status/severity maps to label + tone |
| `projects/dashboard/src/app/automation/automation-board.ts` | **Create** — OnPush board, media-ui primitives, `--mm-component-*` styles |
| `projects/dashboard/src/app/automation/automation-board.spec.ts` | **Create** — mock facade signals; assert loading/empty/error/partial/ready DOM |
| `projects/dashboard/src/app/app.routes.ts` | Wire `AutomationBoard` + `AutomationFacade` on `DashboardPage` |
| `projects/dashboard/src/app/app.spec.ts` | Only if home smoke assertions need updating for new board heading text |

**Do not create:** HTTP adapter, env files, Reports cron UI, Storybook story unless a reusable tile is promoted to `media-ui` (ticket says “if promoted” — default: skip Storybook for v1).

## Step-by-step tasks (ordered, checkboxes)

- [ ] **1. Extend the shared port (additive only)**  
  In `media-stack-api.ts`, append automation types, `getAutomationSummary()` to `MediaStackApi`, `normalizeAutomationSummary`, and `summarizeAutomationHealth`. Do not rename or reorder existing torrent/calendar methods. Coordinate with parallel FDM-488/489/490 agents: touch only new symbols at the bottom of the file / end of the interface.

- [ ] **2. Cover normalizers with unit tests**  
  In `media-stack-api.spec.ts`, add cases for: healthy DTO → domain; unknown `status` → `'unknown'`; `services: null` + `unavailable.services` → availability `unavailable`; `[]` → `empty`; missing `generatedAt` → empty string or guarded fallback; problems sorted by severity preference in `summarizeAutomationHealth`.

- [ ] **3. Extend the mock adapter**  
  In `mock-media-stack-api.ts`, add `DEMO_AUTOMATION_SUMMARY` with ≥3 services (mix of healthy + one degraded/down), 2–4 preview items, 1–2 actionable problems, ISO `generatedAt`. Implement `getAutomationSummary()` returning a deep shallow-copy. For tests, either:
  - expose `setAutomationScenario('default' | 'empty' | 'partial' | 'fail')`, or
  - keep failure injectable only via facade test doubles (preferred for facade; mock file still needs a deterministic default + one partial fixture used by mock specs).

- [ ] **4. Extend mock specs**  
  Assert default summary keys, service ids stable, and a partial fixture marks preview unavailable while services remain present.

- [ ] **5. Implement `AutomationFacade`**  
  Copy structure from `CalendarFacade` (read-only poll). Map API result through `normalizeAutomationSummary`. Derive status:
  - reject → `error` + user-facing message “Automation is temporarily unavailable. Try again.”
  - success + all sections empty and none unavailable → `empty`
  - success + any unavailable → `partial` (still set summary)
  - else → `ready`  
  Start polling once; clear interval on destroy.

- [ ] **6. Facade specs**  
  Use inline `MockApi implements MediaStackApi` (stub other methods like calendar facade tests do once calendar methods exist). Cover: ready, empty, partial, error, single polling interval, stop on destroy.

- [ ] **7. Format helpers**  
  Map each `AutomationServiceStatus` and `AutomationProblemSeverity` to `{ label, tone }` with tones from `'success' | 'warning' | 'danger' | 'info'`. Labels must be human language (“Healthy”, “Degraded”, “Down”, “Unknown”, “Needs attention”, etc.). Format `generatedAt` for display (locale-friendly short datetime; empty → “Generated time unavailable”).

- [ ] **8. Build `AutomationBoard`**  
  Standalone OnPush component `mm-automation-board`. Inject facade; `startPolling()` in constructor. Template branches for all five statuses. Services sorted unhealthy-first via facade computed or board helper using `summarizeAutomationHealth` / status rank. Use `aria-labelledby`, `aria-live="polite"` on dynamic lists. No config actions.

- [ ] **9. Board specs with mock facade**  
  Pattern from `downloads-board.spec.ts`: `signal()` stubs + `vi.fn()` for `refresh`/`startPolling`. Assert text for loading, empty, error+retry, partial unavailable copy, ready tiles showing a danger/warning label for unhealthy service and calm healthy label.

- [ ] **10. Wire into DashboardPage**  
  Update `app.routes.ts` imports, providers, and template. Keep calendar/downloads working. Do not add routes or sidebar links.

- [ ] **11. Run tests**  
  `npx ng test dashboard --watch=false` (or repo’s equivalent `npm test -- --watch=false`). Fix compile errors from `MediaStackApi` implementors: every test double that `implements MediaStackApi` must add `getAutomationSummary` (search for `implements MediaStackApi` and update stubs in facade specs / app tests).

- [ ] **12. Manual browser check**  
  Open `/`, confirm Automation section renders demo data, Retry works when forcing error via temporary mock fail (or leave covered by unit tests if mock has no UI toggle).

## Testing plan

| Layer | File | Must prove |
|-------|------|------------|
| Normalizers | `media-stack-api.spec.ts` | DTO → domain; partial/unavailable; unknown status |
| Mock | `mock-media-stack-api.spec.ts` | Deterministic default; partial fixture |
| Facade | `automation.facade.spec.ts` | `loading \| ready \| empty \| partial \| error`; poll lifecycle |
| Format | `automation-format.spec.ts` | Every status/severity has non-empty label + valid tone |
| Board | `automation-board.spec.ts` | DOM for each status; retry calls `refresh`; semantic status text present (not color-only) |
| Shell | `app.spec.ts` (if needed) | Home still navigable; optional assert “Automation” heading |

**Acceptance-oriented scenarios to encode in board/facade tests:**

1. All healthy → calm success/info labels; no danger tone unless a problem exists.
2. One down service + healthy peers → down service appears first with “Down” label; healthy still visible but quieter.
3. Preview `unavailable`, services present → `partial` status; services tiles usable; preview shows unavailable message.
4. Full rejection → error card + Try again recovers when API succeeds again.

Storybook a11y for a promoted service-tile: **skip unless** extracting a shared primitive into `media-ui` (not required for slice completion).

## Risks / coordination (esp. shared MediaStackApi with FDM-488/489/490)

| Risk | Mitigation |
|------|------------|
| Merge conflicts in `media-stack-api.ts` / `mock-media-stack-api.ts` | Only **append** new methods and types; never rewrite existing downloads/calendar symbols. Prefer adding new blocks at file end. Rebase early. |
| Test doubles break compile | Grep `implements MediaStackApi` / `MediaStackApi` mocks after adding the method; update every stub with `getAutomationSummary(): Promise.resolve(...)` or reject. |
| Overlap with FDM-488 cron logs | Automation summary must **not** include raw run history tables. Problems are short actionable strings only; deep history belongs on Reports. |
| FDM-491 layout rewrite | Keep board self-contained (`:host { display: block }`). FDM-491 will reposition; do not hard-code asymmetric grid in this ticket. |
| FDM-492 live adapter | Name DTO fields to be mappable from `homepage-actions`; do not call HTTP or add `HttpClient` providers now. If live JSON differs later, adjust normalizer only. |
| Partial vs empty confusion | Encode availability enum in normalizer tests so UI never treats “unavailable” as “nothing to report”. |

## Out of scope

- Configuration-changing actions (restart, enable/disable jobs, edit schedules)
- Raw cron / run history UI (FDM-488 Reports)
- HTTP/live `MediaStackApi` adapter, proxy, env switching (FDM-492)
- Asymmetric home composition and motion (FDM-491)
- New sidebar route or `/automation` page
- Promoting tiles to Storybook / `media-ui` unless a second consumer appears
- Backend or `homepage-actions` changes

## Acceptance criteria mapping

| AC / behavior | How this plan satisfies it |
|---------------|----------------------------|
| Visitor sees healthy vs unhealthy and next action without raw logs | Services + Problems tiles with semantic labels; preview for upcoming work; no log dump |
| Extend port + mock for automation summary | `getAutomationSummary` + `normalizeAutomationSummary` + mock demo/partial fixtures |
| Flat status-led tiles for service state, preview, problems, generated time | `AutomationBoard` three regions + timestamp in heading |
| Loading / empty / partial / failure | Facade status machine + board `mm-state-card` / partial banner |
| Semantic status not color alone | `MmStatus` always shows text labels from format maps |
| Partial or absent preview remains useful | `availability.preview === 'unavailable'` renders explicit copy; other sections still render |
| Healthy noise stays calm | Sort unhealthy first; healthy tones are success/info; no alert chrome for all-clear |
| No config-changing actions | Facade has refresh/poll only |
| Raw cron history → Reports | Problems are summaries only; no cron list |
| Destination = dashboard board, not sidebar | Wire only on `DashboardPage`; no nav/route |
| Facade-derived-state + health-combination component scenarios | Covered in facade + board specs |
| Browser acceptance | Manual `/` check after unit tests green |
