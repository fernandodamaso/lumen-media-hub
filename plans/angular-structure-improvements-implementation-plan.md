# Angular structure improvements implementation plan

## Objective

Harden the existing Angular 22 architecture without changing its successful shape. Completion means stricter compiler and lint safeguards, trustworthy HTTP decoding, race-safe polling, corrected component semantics/accessibility, appropriate route loading, and a verified zoneless application.

This plan implements the findings in [docs/angular-structure-review.md](../docs/angular-structure-review.md).

## Guardrails and non-goals

- Preserve feature-first folders, component-scoped facades, signals, Storybook, and the `MediaStackApi` port with mock/HTTP adapters.
- Preserve Demo and Live behavior, route URLs, theme persistence, and the proxy-owned credential boundary.
- Preserve feature ownership of domain/display models and transformations; `media-stack` owns transport decoding and wire DTOs.
- Do not add NgRx, NgModules, generic `core`/`shared` layers, endpoint repositories, OpenAPI generation, browser auth, or speculative abstractions.
- Do not split `DiscoverFacade`, `MediaStackApi`, or boards based only on file size.
- Do not adopt `withFetch()`: Angular 22 already uses Fetch by default and the feature is deprecated.
- Keep unrelated dirty-worktree changes untouched. Each phase should be independently reviewable and reversible.

## Current baseline

Before implementation, record the exact branch, base SHA, and dirty worktree. The review-time baseline on 2026-07-16 was:

- `npm run lint`: pass;
- `npm test -- --watch=false`: 31 files / 221 tests pass;
- `npm run build`: pass, initial bundle 442.88 kB raw / 110.74 kB transferred, under the 500 kB warning budget;
- `npm run build:storybook`: pass;
- `npm run test:storybook`: 8 suites / 33 tests pass;
- `npm ls --depth=0`: pass.

The Storybook test run warns about a Jest haste module-name collision with a second `package.json` under `.worktrees/repo-simplification`. Treat removing that test-discovery noise as tooling hygiene; do not delete the worktree.

## Work package 1 — compiler and lint guardrails

### Changes

1. In `tsconfig.json`, enable:
   - `compilerOptions.strict: true`;
   - `angularCompilerOptions.strictTemplates: true`;
   - `angularCompilerOptions.strictStandalone: true` if Angular 22 accepts it across app, tests, and Storybook without a compatibility exception.
2. Fix the resulting TypeScript and template errors without weakening the flags or adding blanket assertions.
3. Add `angular-eslint` packages compatible with Angular 22 and ESLint 9.
4. Extend `eslint.config.js` to lint Angular component TypeScript and templates, including inline templates.
5. Configure a focused rule set:
   - selector prefix/style matching the existing `mm-` convention;
   - OnPush enforcement;
   - template accessibility rules with low false-positive risk;
   - no duplicate/conflicting formatting rules already covered by Prettier.
6. Align the Angular component schematic prefix with `mm`, or document why the root `app-root` is the sole exception.
7. Add `ChangeDetectionStrategy.OnPush` to `app.ts`.
8. Replace the repeated `_summary()` read and non-null assertion in `automation.facade.ts` with one narrowed local value.

### Acceptance criteria

- App, tests, and Storybook compile with TypeScript strictness and strict template checking enabled.
- No new `any`, `!`, `@ts-ignore`, disabled lint blocks, or weakened compiler flags are introduced merely to make the phase pass.
- ESLint covers `.ts` and `.html`, including inline component templates.
- Existing selectors are accepted intentionally, not by disabling selector checks globally.

### Verification

Run the full validation matrix at the end of this package. Commit compiler remediation separately from unrelated functional changes so regressions are easy to identify.

## Work package 2 — HTTP contract validation

### Changes

1. Inventory every `HttpMediaStackApi` endpoint and classify fields as:
   - required transport identity/state;
   - optional display metadata;
   - explicit soft-failure envelope data.
2. Add small endpoint-specific runtime decoders/guards under `media-stack`; reuse basic record/string/number/array helpers where they genuinely reduce duplication.
3. Validate every member of successful arrays before calling feature mapping functions.
4. Reject malformed required fields rather than manufacturing IDs, timestamps, or apparently valid empty values.
5. Preserve the existing distinction between hard failures and feature-visible `{ ok: false }` soft responses.
6. Change the unfiltered Jellyfin library result so one failed source is represented as degraded/partial availability instead of silently returning a complete-looking list. Keep filtered calls strict for the requested kind.
7. Keep feature-specific domain/display mapping in feature `*-format.ts` files. Do not move presentation policy into the HTTP adapter.

### Tests

For every endpoint, cover:

- successful payload;
- malformed/null envelope;
- missing required field;
- invalid array member among otherwise valid members;
- `{ ok: false }` behavior where supported;
- transport error normalization;
- partial movies/series availability and total failure.

### Acceptance criteria

- Invalid backend contract data fails at the adapter boundary with endpoint-specific errors.
- No required identity or freshness field is silently synthesized.
- UI/facades can distinguish full, partial, and failed library loads.
- Mock and HTTP adapters remain behaviorally compatible at the `MediaStackApi` boundary.

## Work package 3 — polling and async correctness

### Changes

1. Use `ReportsFacade` as the local reference for generation checks and last-good-data retention.
2. Update `DownloadsFacade`, `CalendarFacade`, `AutomationFacade`, and the per-source loads in `DiscoverFacade` so scheduled refreshes cannot overlap for the same resource.
3. Ensure a superseded response cannot overwrite newer state, including two requests for the same Discover tab/filter.
4. Keep initial loading failures distinct from background refresh failures. A background failure must retain last-good content and show a non-destructive notice.
5. Keep mutation busy/error state separate from poll refresh state.
6. Retain the existing `DestroyRef` timer cleanup. Standardize whether the route/board calls an explicit `startPolling()` only where that makes ownership clearer; constructor placement alone is not a target.
7. Prefer the existing Promise/signal model. Introduce RxJS polling only if cancellation, retry/backoff, or multi-stream composition demonstrably removes more code than it adds.

### Tests

Use deferred promises and fake timers to prove:

- a slow poll cannot overlap another scheduled poll;
- a late older response cannot replace a newer result;
- destruction stops future scheduling;
- refresh errors retain prior data;
- source/tab changes cannot leak stale state;
- double-clicked mutations remain guarded.

### Acceptance criteria

- At most one scheduled request per resource is active.
- State transitions are deterministic under reordered promise completion.
- No facade reports an exclusive error state while valid retained data is still being shown.

## Work package 4 — component semantics and accessibility

### `MmCard`

- Delete `AfterViewChecked`, `ElementRef`, `querySelector`, attribute toggling, and inline-style mutation.
- Use the existing CSS `:has()`/`:empty` structure to hide absent header/footer regions.
- Test cards with no header, heading only, actions only, and footer content/actions.

### `MmStatus`

- Make the visual badge neutral by default.
- Add an explicit input for live-announcement behavior only where dynamic status must be announced.
- Remove nested/duplicate live-region semantics at call sites.

### Discover source selector

- Prefer native buttons with `aria-pressed` inside a labelled group.
- If radio semantics are retained instead, implement roving `tabindex`, arrow-key selection, Home/End behavior, and focus tests. Do not keep partial radio semantics.

### `MmPoster` and theme picker

- Change the poster primitive's root from `<article>` to a neutral wrapper; feature consumers own document structure.
- Register destruction cleanup for the theme picker's pending “saved” timeout.

### Acceptance criteria

- Storybook interaction/a11y tests pass without nested live regions or partial radio behavior.
- Keyboard-only operation covers the Discover source selector.
- UI appearance and public component behavior remain compatible unless the semantic change is intentional and documented.

## Work package 5 — routing and zoneless platform alignment

This package has two separate commit/rollback gates.

### 5A. Route loading

1. Keep the `/` dashboard page eagerly imported as the primary landing route.
2. Convert `/reports` and `/discover` to `loadComponent` dynamic imports.
3. Remove `withEnabledBlockingInitialNavigation()` for the client-rendered application.
4. Verify direct navigation, redirect behavior, route titles, and chunk loading.

Acceptance:

- `/`, `/dashboard`, `/reports`, `/discover`, and the wildcard redirect behave as before.
- The production output contains separate lazy chunks for Reports and Discover.
- The initial bundle does not regress beyond the existing budget.

### 5B. Zoneless

1. Remove `provideZoneChangeDetection` from `app.config.ts`.
2. Remove `zone.js` from application build polyfills and any test/Storybook setup that explicitly loads it.
3. Remove the `zone.js` dependency only after usage search and all validation gates pass.
4. Do not add `withFetch()` or redundant zoneless providers unless an Angular 22 integration specifically requires one.
5. Exercise timer-driven refresh, theme updates, router navigation, busy states, Storybook interactions, and third-party Lucide components.

Acceptance:

- App, unit tests, and Storybook run without ZoneJS.
- Every asynchronous state change used by the UI still schedules rendering through a supported zoneless notification path.
- The zoneless change remains independently revertible from lazy routing.

## Work package 6 — docs, app smoke coverage, and CI finish

### Changes

1. Correct `docs/architecture.md` so credentials remain a proxy/server concern; remove the stale optional browser `ACTIONS_TOKEN` claim.
2. Document the actual `mm-` selector convention and root `app-root` exception.
3. Add a small browser-level application smoke suite for direct navigation to `/`, `/reports`, and `/discover`, primary landmarks, and a basic theme change.
4. Run Storybook static build and interaction/a11y tests in CI if the repository's CI environment owns that responsibility.
5. Exclude `.worktrees` from the Storybook/Jest test discovery path to remove the module-name warning without modifying or deleting worktrees.

### Acceptance criteria

- Architecture documentation matches runtime credential and selector behavior.
- At least one test validates the assembled routed application rather than only isolated components.
- CI runs the same essential validation gates used locally, or the deliberate exclusions are documented.

## Validation matrix

Run after every work package in proportion to its scope, and run the complete matrix before completion:

```powershell
npm run lint
npm test -- --watch=false
npm run build
npm run build:storybook
npm run test:storybook
npm ls --depth=0
git diff --check
```

For routing and zoneless packages, also start the built or development app and execute the browser route smoke suite. For HTTP boundary changes, perform a read-only Live-mode smoke against the local API after mock/contract tests pass; mutating endpoints require a controlled test window.

## Sequencing and review boundaries

```text
compiler/lint
      |
      +--> HTTP validation --> async/polling
      |                           |
      +--> component/a11y --------+
                                  |
                         lazy routes --> zoneless
                                  |
                            docs/smoke/CI
```

- Strictness comes first so later work benefits from stronger checks.
- HTTP validation precedes polling changes so async tests operate on trustworthy contracts.
- Component/accessibility work can be reviewed independently after strictness.
- Zoneless is last among runtime changes and has its own rollback boundary.
- Do not combine all work packages into one pull request. Prefer reviewable packages with the relevant tests and before/after evidence.

## Completion criteria

The plan is complete when:

- TypeScript strictness, strict Angular templates, and Angular template linting are active without blanket suppressions;
- HTTP responses are validated per endpoint and partial availability is explicit;
- scheduled refreshes cannot overlap or apply stale results;
- the identified card, status, source-selector, poster, and timeout issues are fixed and accessibility-tested;
- secondary routes are lazy, initial navigation is appropriate for CSR, and the app is verified without ZoneJS;
- architecture docs and a routed-app smoke suite match the implemented system;
- the complete validation matrix passes, with any environmental warning documented rather than hidden.
