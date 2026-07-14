# Angular Architecture Refactor and API-Ready Structure

## Summary

- Reorganize the application feature-first, avoiding generic `components`, `services`, `models`, and `utils` dumping grounds.
- Use external `.html` and `.scss` files for pages and substantial components. Inline resources remain acceptable for genuinely tiny leaf primitives and test hosts—Angular supports both; external files are preferable once the component has meaningful structure or styling.
- Preserve Storybook as the design-system showcase, including accessibility checks, documentation, themes, and interaction tests. Remove only the duplicate in-app `/ui` catalog.
- Prepare Angular to replace the `D:\media` React dashboard through a staged rollout. The current React service remains untouched and operational during this refactor.

## Implementation Changes

### Application structure

Organize `projects/dashboard/src/app` around these responsibilities:

- Application shell: bootstrap, routes, top-level layout, navigation, and environment providers.
- Feature directories: `dashboard`, `downloads`, `reports`, and `discover`, each owning its pages, facade, domain models, mappings, and tests.
- `ui`: application-wide design-system primitives, tokens, and themes.
- `media-stack`: the shared integration boundary containing the API port, HTTP adapter, mock adapter, provider, and backend wire contracts.
- Do not introduce `core`, `shared`, or additional abstraction layers unless they acquire a concrete responsibility that does not fit these boundaries.

For component resources:

- Pages, boards, cards, dialogs, navigation, and the theme picker use matching `.ts`, `.html`, and `.scss` files.
- Tiny presentational primitives may retain inline templates/styles when each remains trivial.
- Storybook stories remain separate `.stories.ts` files.
- Inline test-host templates remain allowed.
- Preserve the existing concise component naming; do not mechanically add `.component` suffixes.

Simplify while moving code:

- Remove redundant `standalone: true`, facade passthrough methods, identity helpers, duplicate scripts, unused detail state, and obsolete provider/Pages branches.
- Replace custom state machinery with native Angular or HTML behavior where it reduces code without changing UX.
- Preserve the existing `/`, `/reports`, and `/discover` behavior and both Demo and Live modes.

### Design system and Storybook

- Fold the single-consumer `media-ui` library into the dashboard's `app/ui` area; update imports before removing the library project and `ng-packagr`.
- Keep design tokens and themes centralized, while component-specific styles stay beside their components.
- Retarget Storybook configuration, TypeScript includes, and global style imports from `projects/media-ui` to `projects/dashboard/src/app/ui`.
- Maintain one focused CSF story file per primitive, with useful controls, states, theme coverage, keyboard interactions, and accessibility assertions.
- Preserve the a11y/docs addons, Compodoc, theme toolbar, play functions, local Storybook command, and static `build:storybook`.
- Add the static Storybook build to CI.
- Delete the in-app `/ui` gallery only after Storybook provides equivalent component coverage.
- Storybook remains buildable and locally viewable; public Storybook hosting is not introduced in this refactor.

### `D:\media` API boundary

- Keep one `MediaStackApi` port and injection token because it has two legitimate implementations: HTTP and deterministic mock.
- Move the port and both adapters out of `downloads`; components continue to depend on feature facades, and facades depend on the port. Components never inject HTTP or mock adapters directly.
- Keep backend wire-response types internal to `media-stack`, grouped by API area. Keep UI/domain models and display transformations owned by their corresponding features.
- Keep the handwritten client: the backend has no OpenAPI contract, so generated clients or an additional API library are not justified.
- Retain `environment.apiBaseUrl = '/api'` and select Demo versus Live through the existing provider boundary.
- Do not add a browser token service or authentication interceptor. Development and production proxies remain responsible for injecting `X-Actions-Token`.
- Normalize transport errors and malformed envelopes at the adapter boundary while preserving existing `ok: false` action semantics.
- Do not prebuild methods for unused backend endpoints. Add endpoints when a feature consumes them.
- Preserve the complete stateful Discover contract, including active/history recommendations, feedback, request state, pending synchronization, reconciliation, generation state, and request-more behavior.

### Staged React-to-Angular replacement

- The structural refactor does not modify or delete `D:\media\dashboard`; React remains the active service.
- Validate Angular Live mode alongside React on its normal development port using the existing `/api` development proxy.
- Compare Angular requests against the running Python backend and the current React API client during contract verification.
- After Angular reaches behavioral parity, create a separate cutover change that builds Angular into the existing dashboard container while retaining its Nginx `/api` reverse proxy and server-side token injection.
- Production switching requires explicit approval and successful parity checks. Retain the last working React image/source as the rollback path.
- Deleting the React implementation is a separate later decision, never part of the initial Angular cutover.

## Interfaces and Compatibility

- `MediaStackApi` keeps its existing consumer-facing behavior; moving its import path must not alter feature semantics.
- UI imports move from the `media-ui` package entry point to the local `app/ui` boundary.
- No API token, backend host, or `127.0.0.1:8085` address becomes browser-visible.
- Existing routes, deep links, theme persistence, Demo badge, responsive behavior, and accessibility behavior remain compatible.
- Remove dependencies only after usage checks and successful builds; likely candidates include `ng-packagr` and other library-only or demonstrably unused packages. Storybook, Compodoc, and their required Angular tooling remain.

## Test and Acceptance Plan

- Capture the dirty-worktree baseline and preserve unrelated user changes.
- Before removing `media-ui`, run its existing tests to establish parity.
- At each refactor gate run lint, dashboard tests, dashboard production build, Storybook static build, and `git diff --check`.
- Add HTTP adapter tests for paths, verbs, query parameters, request payloads, successful envelopes, `ok: false`, malformed responses, and network failures.
- Add provider tests proving Demo uses the mock adapter and Live uses the HTTP adapter.
- Keep facade tests focused on loading, error, refresh, mutation, and state-preservation behavior.
- Exercise Storybook interaction and accessibility checks for every design-system primitive.
- Browser-test Demo mode across all supported routes and themes.
- Run a read-only Live smoke test against `D:\media`; mutating operations require a controlled test window and restoration of the previous state.
- Completion requires the dashboard, Storybook, and both API modes to pass while the existing React dashboard remains available.

## Assumptions

- “Angular will replace React” means staged replacement, because React currently provides the more complete and reliable service.
- Storybook is permanent project infrastructure and the canonical design-system showcase.
- The `/ui` application route is redundant once Storybook coverage is complete.
- The existing same-origin `/api` proxy architecture is retained for both security and deployment simplicity.
- This is a net-simplification refactor: external templates increase the number of purposeful files, while dead code, duplicate catalogs, the library boundary, and unnecessary dependencies are removed.
