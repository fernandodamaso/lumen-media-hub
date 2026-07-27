# Code Review — feat/skeleton-shimmer-loading

> **Superseded source report.** Findings were verified, deduplicated, reprioritized, and merged into [`reviews/feat-skeleton-shimmer-loading-review.md`](reviews/feat-skeleton-shimmer-loading-review.md). Keep this file as historical reviewer output; use the consolidated report for fixes.

Two-axis review of the unpushed commits and uncommitted changes on `feat/skeleton-shimmer-loading`, relative to `origin/main` (merge-base `71d739e`).

- **Unpushed commits** — `git diff origin/main...HEAD` (12 commits, 766e64d…9d5c90b; downloads-card / mm-progress work)
- **Uncommitted changes** — `git diff HEAD` (~2493 insertions, 31 files; automation modal + skeleton-shimmer loading)

Spec sources:

- Committed work: `.opencode/plans/1785076160366-stellar-river.md` (Downloads Card Polish)
- Uncommitted automation work: `.opencode/plans/1785076424638-neon-knight.md` (Premium Automation Service Dialog)
- Skeleton-shimmer loading work: **no spec available** — not reviewed against requirements

## Standards

No hard violations of documented standards. AGENTS.md "do not" list respected (no token interceptor, SABnzbd stays Demo-only, no backend retargeting); wire DTOs stay in `media-stack`; `mm-` prefix, OnPush, signals, `@if`/`@for` house style all hold (architecture.md "Contribution baseline"). All findings below are baseline-smell judgement calls.

### Committed diff (766e64d…9d5c90b)

- **Mysterious Name** — `downloads-card.spec.ts:223`: `// ponytail: mock doesn't derive summary…` — a marker no other file in the repo uses; the explanation is fine, the tag is not house style.
- **Duplicated Code / fragile string parsing** — `downloads-format.ts:70`: `formatRateParts` recovers value/unit by splitting `formatRate`'s output on the last space instead of formatting directly; couples to `formatRate`'s exact output shape (the spec encodes that coupling deliberately).
- **Duplicated Code** — `media-stack-api.providers.ts:20`: the `switch` over scenario names restates the `DownloadsScenario` union members; two sources of truth (a const array would be one).

### Uncommitted diff (`git diff HEAD`)

- **Duplicated Code (dead rule)** — `ui/button.ts:50-53`: `.mm-button--primary` re-declares the base `.mm-button` `background`/`color` verbatim; pure no-op rule added only so a CSS-probing spec can find it.
- **Primitive Obsession (notable)** — `dashboard/automation-card.ts:1376`: `ARR_DETAIL_RE` regex-parses the human-formatted display string `service.detail` ("34 missing · 17 shows · 1 queued") back into stats. That data should arrive structured from the facade/mapper, not be reverse-engineered from display text.
- **Repeated Switches** — `automation-card.ts`: `id === 'sonarr' / 'radarr'` string checks recur in `isArrId`, `sectionLabel`, `cardSubtitle`, `parseArrDetail`, `groupDialogItems`. A per-service config map would collapse all five.
- **Duplicated Code** — `automation-card.html`: the show-card poster block is copy-pasted three times (details/summary, `a.show-card`, `span.show-card--static`); the episode-row markup is duplicated anchor-vs-static as well.
- **Model/mapper mismatch** — `automation.models.ts:22-23`: `href`/`posterUrl` declared optional, but both mappers (`automation-format.ts:57`, `live-api.mappers.ts:384`) always set them — forcing two `eslint-disable-next-line no-unnecessary-condition` comments and a dead `(label.charAt(0) ?? '?')` fallback in `automation-card.ts`. Make the fields required instead of suppressing.
- **Speculative Generality** — `automation-card.ts:1381`: `DialogItemRow.code` is always `''`; dead field.
- **Duplicated Code / magic string** — identical `:host-context(mm-dashboard-page.is-dashboard-loading)` blocks in `upcoming-card.scss`, `automation-card.scss`, `library-card.scss` (and `downloads-card.scss` in the committed diff) while `ui/media-ui.scss` adds the same rules globally; cards also hardcode the page's private host class. One home (the global sheet) would do.
- **Duplicated Code** — `app.spec.ts`: the same `useFactory` `latencyMs = 0` provider block three times.
- **Guardrail erosion (judgement)** — `angular.json`: `anyComponentStyle` budget raised 8kB→9kB in both configurations even though commit cf55d0b already shrank the stylesheet; angular-structure-review treats build budgets as a safeguard. Raising to fit beats the purpose.

## Spec

### Committed diff vs stellar-river plan

- **Deviation — header stats while loading.** Spec Task 2.1: "Hide `.dl-stats` during `loading` as well as `empty` (`@if (facade.status() === 'ready')`)". Implementation keeps `@if (facade.status() !== 'empty')` and hides chrome only via `:host-context(mm-dashboard-page.is-dashboard-loading)` — a class that exists only in the *uncommitted* diff. The committed test codifies the deviation: `it('shows dl-stats during loading and ready, hides on empty')`. Committed HEAD alone does not satisfy mockup delta 7.
- **Cross-diff breakage.** Committed `ui/primitives.spec.ts` adds `it('does not transition button text color…')` asserting no `color` in the transition and `css.toContain('mm-button--primary')` — but the `button.ts` change satisfying it is uncommitted. At HEAD the test fails (button.ts:47 still transitions `color`; no `.mm-button--primary` rule). Suite is red on the branch as committed.
- **Scope creep.** Task 1.1 scope was scenario support; the diff adds `withLatency` jitter to ~10 mock methods (`listCalendar`, `getArrLibrary`, `getAutomationSummary`, `listCronLogs`, discover endpoints, etc.), changing demo behavior of every facade — beyond the spec. Minor: ETA fallback changed to `'—'` and footer link gained a hardcoded `→`, neither requested.
- **Mechanism deviation (benign).** Spec Task 2.1: muted bars "by setting `--mm-progress-tone: var(--mm-component-border)` from the card SCSS via `.dl-item--paused mm-progress`". Implementation instead added a `muted` tone to `MmProgressTone` and binds `[tone]`. Same visual result, not the specified approach.

### Uncommitted diff vs neon-knight plan (tasks 1B/2A/3A)

Mostly faithful: `posterUrl` contracts (1B), mapper normalization + tests (2A), stats/heading/details-accordion/direct-link cards/initials fallback/no banner/no external-link icon (3A) all present.

- **Partial — blank normalization.** Spec 2A: "absent/blank input becomes `null`" in `mapAutomationSummary`; implementation is `posterUrl: item.posterUrl ?? null` — a blank `''` survives in the DTO→domain (demo) path; only the live mapper normalizes.
- **Deviation — grouping key.** Spec 3A: "group by existing `href ?? title`"; implementation groups Sonarr rows by title-derived label (`${problemId}::${label}`), not href.
- **Possible contract breach — generic dialogs.** Contract: "Prowlarr/Bazarr/other service details keep their generic severity/problem presentation and ordering." The generic branch lost the `svc-detail__status` pill and `svc-detail__copy` detail line, and severity headings now render only when >1 group — unrequested changes to non-Arr rendering.
- **Scope creep.** `angular.json` style budget raised 8kB→9kB (x2) and `.gitignore` adds `/.playwright-mcp` — not in the plan. The skeleton work also restructured `automation-card.html` chrome, which Task 3A scoped to the dialog only.

## Summary

- **Standards:** 12 findings, all judgement calls — worst is the regex-parsing of the `service.detail` display string back into stats in `automation-card.ts` (Primitive Obsession).
- **Spec:** 9 findings — worst is the red test suite at committed HEAD (`primitives.spec.ts` asserts a `button.ts` change that only exists in the uncommitted diff), plus generic non-Arr dialogs losing their status pill and detail line against the explicit contract.
