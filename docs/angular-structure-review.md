# Angular structure review

Review of how well this project follows modern Angular practice: overall structure, component usage, and gaps worth closing.

**Scope:** `projects/dashboard` (Angular 22)  
**Date:** 2026-07-16

---

## Overall verdict

This is a **well-structured, genuinely modern Angular project** — above average for a codebase this size. The layering in [architecture.md](./architecture.md) is actually followed in code: feature folders own UI + facades + domain models, `media-stack` owns the API port/adapters, and `app/ui` is a real design system rather than a junk drawer.

You are already on the right side of current Angular practice: standalone bootstrap, signals/`computed`, `input()`/`output()`, OnPush, `@if`/`@for`, `inject()`, and component-scoped facades. Boards and pages mostly stay thin; data and mutations sit in facades behind `MEDIA_STACK_API`. That is the correct weight for this app — no NgRx, no NgModules, no fake `shared/` layer.

The main gaps are polish and hardening, not rearchitecture: lazy routes, `strictTemplates`, angular-eslint, safer async/polling, cleaner primitive APIs (`MmButton` events, `MmCard` lifecycle), and optional zoneless when you are ready.

**Structure is a strength; remaining work is incremental upgrades, not a redesign.**

Rough scores:

| Axis | Score | Notes |
|------|-------|--------|
| Structure / layering | ~8/10 | Feature-first, port/adapter, docs match code |
| Component usage | ~7.5/10 | Strong container/presentation split; a few primitive smells |
| Modern idioms | High | Applied as house style, not one-off experiments |

---

## What is working well

### 1. Feature-first layout (not folder-by-type)

The classic trap of `components/`, `services/`, `models/` is avoided. Each area owns its board/page, facade, models, formatters, and tests:

```text
app/
  shell (app.ts, routes, config)
  ui/                 design system
  media-stack/        API port + adapters
  downloads|library|calendar|…   features
```

That matches Angular’s current guidance for scalable apps and the project’s own architecture doc.

### 2. Modern Angular idioms — applied consistently

| Practice | Status |
|----------|--------|
| Standalone components (no NgModules) | Yes |
| `bootstrapApplication` + `ApplicationConfig` | Yes |
| Signal inputs (`input()` / `input.required()`) | Yes |
| Signal outputs (`output()`) | Mostly (e.g. `DiscoverCard`) |
| Signals + `computed` for UI state | Yes |
| `@if` / `@for` / `@switch` control flow | Yes |
| `inject()` DI | Yes |
| `ChangeDetectionStrategy.OnPush` | Consistently on boards, pages, primitives |
| Injection token API port | Yes (`MEDIA_STACK_API`) |
| Component-scoped facades (`providers: […]` on pages) | Yes |

Naming follows the post-v20 style (e.g. `discover-page.ts`, no mechanical `Component` suffix). Accessibility is taken seriously (skip link, labelled regions, `aria-live`, focus styles).

### 3. Clear layering: UI → facade → port → adapter

```text
Boards/pages  →  Feature facades (signals)  →  MediaStackApi  →  Mock | HTTP
                     ↑ domain models in feature folders
                     wire DTOs stay in media-stack/wire
```

- **Port:** `MediaStackApi` + `MEDIA_STACK_API` token  
- **Adapters:** `MockMediaStackApi` / `HttpMediaStackApi` selected by environment providers  
- **Wire DTOs:** quarantined under `media-stack/wire/`  
- **Facades:** private writable signals, public `asReadonly()`, derivations via `computed`

Boards stay mostly presentational; facades own loading/error/empty and mutations. That is the right depth for this app size and is why demo/live modes and port-mocked tests work cleanly.

### 4. Design system is used properly

`app/ui` is a real primitive layer (`MmCard`, `MmButton`, `MmPoster`, `MmStateCard`, `MmSkeleton`, theme tokens), exported via `@app/ui`, documented in Storybook with a11y. Boards consistently compose these instead of reinventing chrome.

### 5. Engineering hygiene

- Facade and contract tests beside features  
- Demo vs live via environment + providers  
- Provider-parity specs (demo → mock, live → HTTP)  
- Storybook + a11y addon + test-runner for UI primitives  
- Explicit UI state machines (`loading | ready | empty | error`)

### Composition example

The home page is a thin orchestrator — pure composition, which is what a container should look like:

```ts
// dashboard-page.ts
@Component({
  selector: 'mm-dashboard-page',
  imports: [CalendarBoard, DownloadsBoard, LibraryBoard, AutomationBoard],
  providers: [CalendarFacade, DownloadsFacade, LibraryFacade, AutomationFacade],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard-page.html',
  styleUrl: './dashboard-page.scss',
})
export class DashboardPage {}
```

---

## Component architecture

```text
App (shell nav + theme)
└─ Router
   ├─ DashboardPage          providers: 4 facades
   │   ├─ LibraryBoard       → LibraryFacade → API
   │   ├─ CalendarBoard      → CalendarFacade → API
   │   ├─ DownloadsBoard     → DownloadsFacade → API
   │   └─ AutomationBoard    → AutomationFacade → API
   ├─ ReportsPage            → ReportsFacade
   └─ DiscoverPage           → DiscoverFacade
       └─ DiscoverCard*      pure presentational

@app/ui: MmCard, MmButton, MmPoster, MmStateCard, …
media-stack: MEDIA_STACK_API → Mock | Http
```

### Smart vs presentational split

| Layer | Role | Quality |
|-------|------|---------|
| **Pages** (`DashboardPage`, `DiscoverPage`, `ReportsPage`) | Route hosts, provide facades, wire events | Clean |
| **Boards** (`*Board`) | Feature widgets on the home grid | Clean; slightly thick templates |
| **Cards** (`DiscoverCard`) | Reusable feature presentational pieces | Strong (`input`/`output`/`computed`) |
| **UI primitives** | Design-system atoms | Strong overall; see exceptions below |

`DiscoverCard` is a model presentational component: required inputs, typed outputs, derived `computed`s, no API knowledge.

---

## Component usage — exceptions

Presentation/container split is respected; primitives are small, OnPush, signal-driven, and Storybook-covered. Three exceptions stand out:

### 1. `MmCard` — real anti-pattern

**Where:** `ui/card.ts` (`AfterViewChecked` + `querySelector`)

It probes its own DOM on every change-detection pass just to hide empty header/footer regions. That hook fires constantly and reaches into the DOM imperatively.

**Idiomatic fixes:**

- Signal-based content queries (`contentChildren` / `contentChild`), or  
- Pure CSS (`:empty` / `:has()` on the wrappers the slots project into)

### 2. `MmButton` — label input instead of content projection

**Where:** `ui/button.ts` (`label` input)

For a design-system primitive, `<ng-content>` is the more flexible, conventional choice. A text `input` blocks markup (icons + labels, wrapping, i18n spans). Host `(click)` also relies on DOM bubbling rather than a designed `output()`.

**Preferred shape:**

- Projected content for the label  
- Explicit `output()` (or a clear host binding) for actions  
- Inputs only for variants, busy/disabled, type

### 3. Side effects in constructors + thick boards

- Boards/facades start polling or `refresh()` from constructors — common but harder to test than an explicit `start()` / `afterNextRender` convention  
- Some board templates (downloads, discover) are multi-state “mini pages”; fine today, extract list rows / tab chrome if they keep growing

---

## Practices not applied (or only partially)

Ordered by impact vs effort.

### High value

| Gap | Why it matters | Direction |
|-----|----------------|-----------|
| **No route lazy-loading** | All feature pages are static imports in `app.routes.ts` | `loadComponent: () => import('…')` for `/`, `/reports`, `/discover` |
| **`strictTemplates` not enabled** | Root `angularCompilerOptions` has injection strictness but no `strictTemplates` | Enable `strictTemplates: true` (and ideally `strictStandalone`) |
| **Still Zone.js** | `provideZoneChangeDetection` + zone polyfill | Move toward `provideZonelessChangeDetection()` once tests cover CD; OnPush + signals already prepare this |
| **No Angular ESLint template rules** | Only `typescript-eslint` | Add `angular-eslint` for templates, selectors, a11y rules |
| **Async race / cancellation** | Facades `await` without abort/version tokens; polling uses `setInterval` | `AbortController`, generation counters, or RxJS `switchMap`/`exhaustMap` so slow responses cannot overwrite newer state |

### Medium value

| Gap | Notes |
|-----|--------|
| **`resource` / `httpResource`** | Optional. Hand-rolled status signals are clear; migrate only where it reduces code. |
| **God-port `MediaStackApi`** | Fine while small; split by domain if the surface grows. |
| **Dependency direction: `media-stack` → features** | HTTP adapter imports mappers from feature `*-format` modules. Pragmatic for one app; cleaner to keep wire→domain mapping inside `media-stack`. |
| **Fat `DiscoverFacade` (~400 lines)** | State + polling + multi-tab caches + request sync — candidate for smaller stores behind one facade. |
| **Inconsistent init** | Library refreshes in facade ctor; downloads start polling from the board. Pick one convention. |
| **Selector prefix** | `angular.json` prefix is `app`; components use `mm-`. Align schematics or document the dual convention. |

### Lower priority

- `NgOptimizedImage` when real poster URLs land  
- Functional interceptors if shared headers/logging appear (auth intentionally stays on the proxy — correct)  
- `@defer` for below-the-fold home boards if LCP becomes an issue  
- Shared `UiStatus` type across facades to avoid per-feature string drift  

---

## What not to add

- No generic `shared/` / `core/` dumping grounds until something has a real cross-cutting job  
- No NgModules  
- No NgRx/Akita for this app size — feature facades + signals are the right weight  
- No OpenAPI client until the backend has a contract  
- No browser auth interceptor (proxy owns the token)

---

## Highest-ROI next steps

1. Enable **`strictTemplates`**.  
2. **Lazy-load** route components.  
3. Add **angular-eslint** (templates + a11y).  
4. Harden facade **async/polling cancellation**.  
5. Fix primitive APIs: `MmCard` lifecycle DOM work; `MmButton` content projection + explicit outputs.  
6. Optionally move toward **zoneless** once the suite is green under it.

---

## Related docs

- [architecture.md](./architecture.md) — workspace layout, data flow, modes, routes  
- [plans/angular-architecture-api-ready-refactor.md](../plans/angular-architecture-api-ready-refactor.md) — intended structure and constraints  
