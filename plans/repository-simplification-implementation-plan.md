# Repository Simplification Implementation Plan

Status: proposed  
Created: 2026-07-13  
Source: whole-repository Ponytail audit

## Goal

Remove redundant product surfaces, package boundaries, state, helpers, and tooling without changing the supported Dashboard behavior or backend contracts.

Expected result:

- roughly 950 fewer repository lines;
- roughly 10 fewer direct dependencies;
- one supported Angular application with Demo and Live modes;
- `/ui` remains the component showcase and accessibility workbench;
- existing Reports, Discover, Library, and Downloads behavior remains intact.

This file is temporary. Delete it in the final cleanup after every acceptance gate passes.

## Scope boundaries

In scope:

- remove the deferred GitHub Pages deployment path;
- remove Storybook and rely on `/ui` plus focused tests;
- fold the single-consumer `media-ui` library into the Dashboard source tree;
- replace avoidable component state with native HTML/CSS behavior;
- delete dead exports, defaults, wrappers, configuration, and dependencies;
- update documentation and CI to describe only supported paths.

Out of scope:

- backend or API contract changes;
- redesigning routes or visual behavior;
- weakening request validation, mutation guards, or environment validation;
- adding a replacement component framework or deployment target;
- responsive-layout or light-theme work.

## Acceptance criteria

1. `/`, `/reports`, `/discover`, and `/ui` retain their current behavior in Demo and Live modes.
2. Reports disclosure, Library keyboard focus, Discover request guards, and Downloads actions retain current accessibility and safety behavior.
3. API tokens, DTO contracts, HTTP mappers, environment validation, and facade-level duplicate-request prevention remain in place.
4. `npm ci`, lint, Dashboard tests, and the production Dashboard build pass from a clean checkout.
5. CI no longer builds Storybook, `media-ui`, or Pages.
6. No Storybook, Pages, Angular-package, Prettier, or unused Forms dependency/configuration remains.
7. The old completed FDM-487 plan and this implementation plan are absent from the finished repository.

## Delivery strategy

Use one reviewable commit per phase. Every phase must pass its gate before the next begins. Do not combine the native-interaction changes with package-boundary removal; their regression risks are different.

Before starting, record a clean baseline:

```powershell
rtk git status --short
rtk npm ci
rtk npm run lint
rtk npx ng test dashboard --watch=false
rtk npm run build:dashboard
rtk npm run build:media-ui
rtk npm run build:storybook
rtk npm run build:pages
```

If a baseline command fails, diagnose it before attributing the failure to this work.

## Phase 1 — Delete dead code and completed planning residue

Delete or simplify only behavior-neutral code:

- delete `plans/FDM-487-implementation-plan.md`;
- delete unused API exports and unused configuration defaults;
- replace JSON serialization clones with `structuredClone` where semantics are identical;
- inline the one-call soft-envelope helper;
- return the service-status string directly;
- remove unused `ThemeService` theme collections/labels;
- remove redundant `standalone: true` declarations;
- remove Discover page pass-through methods that only forward unchanged arguments;
- remove the component-level Discover request guard while retaining facade/API guards;
- replace raw palette duplicates with existing semantic aliases;
- remove `@angular/forms` if the source scan confirms it has no imports.

Do not inline the environment provider factories yet. The Pages file replacement depends on that boundary and will be removed with it in Phase 5.

Gate:

```powershell
rtk npm run lint
rtk npx ng test dashboard --watch=false
rtk npm run build:dashboard
```

Review the diff specifically for removed validation or altered API payloads. None are permitted.

## Phase 2 — Replace avoidable UI state with platform behavior

### Library cards

- replace pointer/focus event handlers and disclosure signals with CSS `:hover` and `:focus-within`;
- preserve focusability, visible focus, and keyboard-revealed actions;
- rewrite the component test to assert the accessible DOM contract rather than private signal state.

### Reports disclosures

- remove the duplicated expanded-state signal and toggle handler;
- use native `<details>` state as the source of truth;
- preserve initial open/closed behavior, accessible labels, and nested disclosure styling;
- update tests to exercise the native element.

Gate:

```powershell
rtk npm run lint
rtk npx ng test dashboard --watch=false
rtk npm run build:dashboard
```

Manually verify the Library and Reports checks in `docs/browser-acceptance.md` with mouse and keyboard before merging this phase.

## Phase 3 — Remove Storybook and unenforced formatting tooling

Before deleting Storybook, inspect its stories and play functions. Port only assertions that cover behavior not already exercised by Dashboard tests. Add them to the nearest existing Vitest component spec; do not recreate a story runner.

Then:

- delete `.storybook/`, story files, the Storybook TypeScript config, and generated screenshots used only by Storybook;
- remove Storybook targets from `angular.json`;
- remove Storybook scripts and its seven direct dependencies;
- remove Storybook CI jobs/steps and documentation references;
- delete the Prettier configuration and dependency because formatting is not enforced by a script or CI;
- update `package-lock.json` through npm, not by hand.

Keep `/ui`; it becomes the only interactive component showcase.

Gate:

```powershell
rtk npm ci
rtk npm run lint
rtk npx ng test dashboard --watch=false
rtk npm run build:dashboard
```

Also verify `/ui` loads and exposes the primitive states formerly inspected in Storybook.

## Phase 4 — Fold `media-ui` into the Dashboard

Move the library sources, styles, and specs under a clear Dashboard-owned directory such as `projects/dashboard/src/app/ui/`.

- move the public barrel with the sources and temporarily retain the `media-ui` TypeScript alias, retargeted to the app-local barrel, to minimize import churn;
- update the global Sass import to the new local path;
- ensure moved specs are included by the Dashboard test configuration;
- delete the Angular library project, packaging configuration, library README, and build target;
- remove `ng-packagr` and the `build:media-ui` script;
- remove the media-ui CI build and package-publication language from docs;
- update architecture documentation to describe UI primitives as application-owned code.

The source move should be structural. Avoid opportunistic component rewrites in this phase.

Gate:

```powershell
rtk npm ci
rtk npm run lint
rtk npx ng test dashboard --watch=false
rtk npm run build:dashboard
```

Confirm the build emits no `dist/media-ui` artifact and every `/ui` example still renders.

## Phase 5 — Remove deferred Pages support and collapse providers

Remove the unsupported deployment branch as one unit:

- delete the Pages build script, Pages environment, and Pages-specific provider file;
- remove Pages configurations and file replacements from `angular.json`;
- remove the Pages npm script and CI build;
- remove Pages deployment instructions and architecture branches from documentation;
- inline the now-single-use provider factories into `app.config.ts`;
- retain empty-base URL handling if it is still required by Demo/Live behavior or tests.

Do not remove URL validation or action-token handling while collapsing providers.

Gate:

```powershell
rtk npm ci
rtk npm run lint
rtk npx ng test dashboard --watch=false
rtk npm run build:dashboard
```

Run the Demo and Live startup smoke checks documented in the README. Live mode may use a local mock API, but it must exercise the real HTTP provider selection.

## Phase 6 — Final repository audit and plan deletion

- update `README.md`, `docs/architecture.md`, and `docs/browser-acceptance.md` to match the final supported topology;
- remove stale screenshots and references to deleted surfaces;
- search for Storybook, Pages, `ng-packagr`, Prettier, Forms, old provider files, and obsolete build commands;
- inspect `package.json` and `angular.json` for one-use aliases or targets introduced during migration;
- delete this plan;
- run the complete final gate from a clean install.

Final gate:

```powershell
rtk git diff --check
rtk npm ci
rtk npm run lint
rtk npx ng test dashboard --watch=false
rtk npm run build:dashboard
```

Browser acceptance must cover navigation, theme persistence, visible keyboard focus, Reports disclosures, Discover request states, Library focus disclosure, and Downloads action totals.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Storybook contains unique interaction coverage | Inventory play functions first and port only missing assertions to existing specs. |
| CSS disclosure changes keyboard behavior | Preserve focusable controls and test `:focus-within` behavior manually and in the DOM contract. |
| Native `<details>` changes initial state | Encode the intended `open` attribute directly and test it. |
| Moving UI sources drops specs or Sass | Retarget the alias first, verify test discovery, and build before deleting library configuration. |
| Pages removal accidentally damages normal URL handling | Keep shared URL tests and remove only Pages-specific branches. |
| Dependency cleanup leaves a stale lockfile | Regenerate with npm and require `npm ci` at every dependency-changing phase. |

## Completion report

The final pull request should report:

- actual lines and direct dependencies removed;
- commits/phases completed;
- supported modes and routes retained;
- commands and browser checks run;
- any audit item intentionally retained, with the concrete reason;
- remaining Sass deprecation warnings or other pre-existing risks.
