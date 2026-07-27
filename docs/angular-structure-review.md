# Angular structure review

Review of the structure, component boundaries, and missing modern Angular practices in `projects/dashboard`.

**Angular version:** 22.0.6
**Reviewed:** 2026-07-16

> **Historical review.** This document records the pre-component-folder layout
> and the state of the application at the review date. See
> [`docs/architecture.md`](architecture.md) for the current frontend structure.

## Overall verdict

This is a well-structured, genuinely modern Angular application. Its architecture is stronger than its current hardening: feature ownership, standalone components, signal-based state, the facade boundary, the API port/adapters, and the local design system are all good choices. The remaining problems are not a reason to redesign the project or introduce a heavier state-management layer.

The main weaknesses are compiler/tooling strictness, HTTP payload validation, polling concurrency, and a handful of component semantics and accessibility details. Those make the project closer to **7.5/10 overall** than “near-perfect,” even though its structural direction is very good.

| Area | Assessment | Why |
|---|---:|---|
| Feature and dependency structure | 8.5/10 | Clear feature ownership and a real two-adapter API seam |
| Component composition | 8.5/10 | Thin route hosts and reusable primitives; a few concrete semantic/lifecycle problems |
| Async and API robustness | 6.5/10 | Good facade shape, but polling can overlap and runtime validation is incomplete |
| Tooling and compiler safeguards | 7/10 | Good tests and Storybook; strict templates and Angular template linting are absent |

The appropriate response is a staged hardening plan, not a broad rearchitecture.

## What is working well

### Feature-first ownership

Each feature owns its page or board, facade, domain models, format helpers, and tests. This avoids generic `components`, `services`, and `models` dumping grounds:

```text
app/
  app.*                         application shell
  ui/                           shared design-system primitives and tokens
  media-stack/                  transport port, adapters, providers, wire DTOs
  dashboard|downloads|library|calendar|automation|reports|discover/
                                 feature UI, state, domain/display transforms
```

The existing boundaries are useful and understandable:

```text
page/board -> feature facade -> MediaStackApi port -> HTTP | mock adapter
                                      |
                                transport/wire DTOs
```

`MediaStackApi` is a justified seam because it has two real adapters. Components do not inject `HttpClient`, and demo/live selection happens at the provider boundary.

### Modern Angular is the project default

The application consistently uses:

- standalone bootstrap and components, with no NgModules;
- signals and `computed` for view state;
- signal inputs and outputs;
- built-in `@if`, `@for`, and `@switch` control flow;
- `inject()` and component-scoped facade providers;
- `ChangeDetectionStrategy.OnPush` throughout feature and UI components;
- typed feature facades exposing readonly signals;
- route pages as composition roots rather than data-access components.

This is coherent house style rather than isolated modernization.

### Components are generally used at the right level

- Pages provide route-scoped facades and wire feature interactions.
- Boards render cohesive dashboard features.
- `DiscoverCard` is a strong presentational component with typed inputs/outputs and no API knowledge.
- `app/ui` is a real, reused primitive layer rather than a catch-all folder.
- Storybook remains the canonical design-system showcase and includes interaction and accessibility coverage.

The current component count and facade size do not justify adding NgRx, a generic store framework, or more abstraction layers.

### Testing and environment seams are unusually good

The repository has colocated facade/contract tests, mock and HTTP adapters, provider-parity tests, production build budgets, Storybook, and Storybook accessibility/interaction checks. The current validation baseline passes lint, 31 Vitest files / 221 tests, the production build, the Storybook build, and 8 Storybook suites / 33 tests. The Storybook test run does emit a Jest haste collision warning because a second `package.json` exists under `.worktrees`.

## Reconciliation with the other reviews

### Agree and add to the review

| Feedback | Reconciled assessment |
|---|---|
| Enable TypeScript `strict` | Agree. The individual flags do not enable `strictNullChecks`; enable `strict: true` and remediate resulting errors deliberately. It is a small config edit, not necessarily a one-line implementation. |
| Enable `strictTemplates` | Strongly agree. This is the highest-value missing Angular compiler safeguard. Angular recommends strict template checking, and it follows TypeScript nullability rules. |
| Add OnPush to the root component | Agree, but low risk/effort. `App` is the only component missing the project convention. |
| Lazy-load routes | Agree with qualification: keep the primary dashboard eager and lazy-load `/reports` and `/discover`. Angular recommends eager loading primary landing pages and lazy loading other pages. |
| Move to zoneless | Agree as a staged migration. Angular 21+ is zoneless by default, while this app explicitly opts back into ZoneJS. Signals and OnPush make it a good candidate, but tests, router behavior, Storybook, timers, and third-party components still need verification. |
| Add angular-eslint | Agree. Add TypeScript and template processors/rules, including selector consistency, accessibility, and OnPush enforcement. Rules only catch what is explicitly configured. |
| Remove the non-null assertion in `AutomationFacade` | Agree. Read `_summary()` once and narrow it; the current double read plus `!` is unnecessary. |
| Replace `MmCard` DOM probing | Strongly agree. `AfterViewChecked` plus `querySelector` runs on every check even though the stylesheet already has enough `:has()` structure to hide empty regions declaratively. Delete the hook and rely on CSS. |
| Harden polling and stale responses | Strongly agree. Several `setInterval` callbacks can start a second request before the first finishes. Reuse the request-generation/in-flight pattern already present in `ReportsFacade`. |
| Remove blocking initial navigation | Agree for this client-rendered app. There is no SSR/hydration requirement that justifies `withEnabledBlockingInitialNavigation()`. |

References: [Angular template type checking](https://angular.dev/tools/cli/template-typecheck), [Angular compiler options](https://angular.dev/reference/configs/angular-compiler-options), [lazy-loaded routes](https://angular.dev/best-practices/performance/lazy-loaded-routes), and [zoneless Angular](https://angular.dev/guide/zoneless).

### Agree with important qualifications

| Feedback | Qualification |
|---|---|
| “No manual subscriptions, therefore no leaks” | Avoiding unmanaged subscriptions is good, but it does not prove leak- or race-free behavior. Timers are cleaned up, yet overlapping promises and late responses remain correctness risks. |
| “The API layer is exemplary” | The port/adapter structure is excellent. Runtime decoding is not yet exemplary: several validators check only the envelope or that a field is an array, then mapping code accepts or fabricates missing values. Each array member and required field should be validated at the transport boundary. |
| Use RxJS polling with `timer`/`exhaustMap` | RxJS is a valid option, not a required best practice. The smaller change is to serialize or version the existing promise-based polling. Adopt RxJS only if cancellation, retries, backoff, or composition make it materially simpler. |
| Pause polling while the page is hidden | Potential optimization, not a current correctness requirement. Add it only after measuring unnecessary traffic or documenting a freshness policy. |
| Move initialization out of constructors | Explicit lifecycle methods can improve clarity, but constructor location is not the main defect. First fix overlapping and stale work; then standardize start/stop ownership where it simplifies tests. |
| Split `MediaStackApi` or `DiscoverFacade` | Do not split for line count. The port is still coherent and earns its abstraction through two adapters. Extract only when a domain has an independent lifecycle or the API surface changes at a different cadence. |

### Do not adopt now

| Feedback | Decision |
|---|---|
| Add `withFetch()` | Do not do this. In Angular 22, Fetch is already the default `HttpClient` backend and `withFetch()` is deprecated as unnecessary. See [`provideHttpClient`](https://angular.dev/api/common/http/provideHttpClient) and [`withFetch`](https://angular.dev/api/common/http/withFetch). |
| Convert local formatting functions to pipes | Not justified. Pure local functions used by OnPush templates are clear; pipes would add files and indirection without solving a demonstrated problem. |
| Replace `MmButton.label` with projected content now | Current call sites use plain text and the input supports a consistent busy state. Projection becomes worthwhile if rich labels or localization markup actually appear. The current API is not a material defect. |
| Move all wire-to-domain mapping into `media-stack` | Preserve the intended ownership: `media-stack` validates transport/wire shapes; features own domain and display transformations. The HTTP adapter may compose those transformations without moving feature policy into transport code. |
| Adopt `resource`/`httpResource` broadly | Optional, not an objective. Existing facades express mutation, polling, partial data, and cached state clearly. Migrate only where a concrete facade becomes simpler. |
| Add interceptors, `@defer`, `NgOptimizedImage`, route-level providers, or a shared `UiStatus` | These are conditional tools, not missing practices. Add them only when authentication/headers, measured performance, real image URLs, provider lifetime, or actual shared behavior requires them. |

## Concrete gaps to fix

### 1. Compiler and lint safeguards

`tsconfig.json` does not enable TypeScript `strict` or Angular `strictTemplates`. The ESLint configuration also lacks Angular TypeScript/template rules. This allows nullability and template mistakes that the framework can catch before runtime.

Add strictness as its own change, fix only errors it exposes, then add angular-eslint with a deliberately chosen rule set. Also align the `mm-` selector convention with the Angular schematic/lint configuration instead of leaving `angular.json` at the unrelated `app` prefix.

### 2. HTTP boundary validation and partial availability

`requireArrayField` proves that a field is an array, but not that its elements match the endpoint contract. Several mappers then default required values to empty strings, `unknown`, composite fallback IDs, or the current timestamp. This can turn backend contract drift into plausible-looking UI data.

The adapter should:

- validate each successful endpoint payload and every array member;
- distinguish optional display data from required identity/state fields;
- reject malformed required data instead of manufacturing identity or freshness;
- preserve explicit `{ ok: false }` semantics where the feature contract needs them;
- represent partial library availability rather than silently returning the successful half as though both sources loaded.

Keep transport decoding in `media-stack`; keep feature/domain transformations in their feature folders. Do not introduce a repository-per-endpoint layer.

### 3. Polling concurrency and stale writes

`DownloadsFacade`, `CalendarFacade`, `AutomationFacade`, and `DiscoverFacade` can overlap interval-triggered requests. Tab/source guards in Discover prevent some cross-tab writes, but they do not prevent an older request for the same source from overwriting a newer result. `ReportsFacade` already demonstrates the right local pattern with a request generation counter and retained last-good data.

Use one consistent policy per facade:

- never overlap scheduled polls for the same resource;
- ignore responses from superseded requests;
- retain last-good data on refresh failure;
- keep initial-load errors distinct from refresh/mutation notices;
- stop timers on destruction, as the project already does.

### 4. Primitive semantics and accessibility

Concrete issues:

- `MmCard` mutates the DOM during `AfterViewChecked`; delete this and use the existing CSS structure.
- `MmStatus` always creates a live region via `role="status"`, including static decorative badges and nested live regions. Make live announcement behavior opt-in.
- Discover source buttons use `role="radio"` without radio-group keyboard behavior. The simpler native solution is ordinary buttons with `aria-pressed`; otherwise implement roving focus and arrow-key navigation fully.
- `MmPoster` owns an `<article>`, which can create inappropriate nested/duplicate article semantics when consumers already own the content container. Make the primitive's wrapper neutral.
- `MmThemePicker` should clear its pending timeout on destruction.

These changes should be captured in component specs and Storybook accessibility checks.

### 5. Route loading and change detection

Keep `/` eager because it is the primary landing route. Convert `/reports` and `/discover` to `loadComponent`, and remove blocking initial navigation unless SSR/hydration is introduced later. Add OnPush to `App`.

Move zoneless in a separate, reversible commit after the strictness and async work. Because Angular 22 is zoneless by default, the migration is principally removal of the explicit ZoneJS opt-in, build/test polyfills, and dependency—not adding deprecated or redundant provider configuration.

### 6. Documentation and end-to-end confidence

`docs/architecture.md` still describes an optional browser-facing `ACTIONS_TOKEN`, while the current architecture deliberately keeps mutation credentials in the proxy/server boundary. Correct that drift. Add a small route smoke test covering direct navigation to `/`, `/reports`, and `/discover`; the existing unit and Storybook coverage does not exercise the application as a routed whole.

## Practices that should remain unchanged

- Keep standalone components, signals, built-in control flow, and component-scoped facades.
- Keep Storybook as the design-system showcase.
- Keep one `MediaStackApi` port while the surface remains cohesive and both mock/HTTP adapters are valuable.
- Keep feature-owned domain/display models and transformations.
- Do not add NgRx, NgModules, a generic `shared`/`core` hierarchy, generated API clients without a backend contract, or browser token handling.
- Do not split components or facades merely to reduce line counts.

## Recommended order

1. Compiler strictness and Angular ESLint.
2. HTTP contract validation and explicit partial availability.
3. Polling/stale-response correctness.
4. Component semantics and accessibility.
5. Lazy routes, non-blocking navigation, then zoneless as a separate gate.
6. Documentation cleanup and an application route smoke test.

The executable work packages, files, acceptance criteria, validation matrix, and rollback boundaries are in [angular-structure-improvements-implementation-plan.md](../plans/angular-structure-improvements-implementation-plan.md).

## Related documents

- [architecture.md](./architecture.md)
- [angular-architecture-api-ready-refactor.md](../plans/angular-architecture-api-ready-refactor.md)
