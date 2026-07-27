# Code review: `feat/skeleton-shimmer-loading`

> **Superseded source report.** Findings were verified, deduplicated, reprioritized, and merged into [`feat-skeleton-shimmer-loading-review.md`](feat-skeleton-shimmer-loading-review.md). Keep this file as historical reviewer output; use the consolidated report for fixes.

**Date:** 2026-07-26
**Fixed point:** `main` (`71d739e`)
**Scope:** 12 unpushed commits + staged WIP (no upstream)
**Axes:** Standards only (Spec skipped — no originating spec)

## Commits reviewed

```
9d5c90b fix(downloads): keep rate icons and values on one meta line
cf55d0b style(downloads): dedupe shared rules to shrink card stylesheet
070ba78 fix(downloads): mute stalled-state progress bars via mm-progress muted tone
0d210a8 fix(downloads): show em dash instead of Complete for stalled items
7e58a49 test(downloads): address spec review findings
571216c test(downloads): cover polished card behavior and formatRateParts
e90e026 refactor(downloads): bind header rate parts once via @let
095e556 feat(downloads): polish card states to match design mockup
2042198 fix(ui): address mm-progress shimmer review findings
6742b7e fix(mock): satisfy typed lint in demo scenario factory
bf4377e feat(mock): add downloads scenarios for demo mode
766e64d feat(ui): add gradient fill and opt-in live shimmer to mm-progress
```

Plus staged WIP: skeleton shimmer, card loading skeletons, automation/library/metric/upcoming cards, `media-ui.scss`, `docs/design/modal-concepts.html`, automation format/models, etc.

---

## Standards

### Documented violations

**`media-ui.scss` + `mm-dashboard-page.is-dashboard-loading`** — Hard.
`architecture.md` limits `app/ui` to design tokens/primitives; `angular-structure-review.md` keeps `app/ui` as a reused primitive layer. Page-host loading chrome (`.card__*` under `is-dashboard-loading`) belongs in dashboard styles, not the shared token sheet.

**`automation-card.ts` (`parseArrDetail`, `groupDialogItems`, `EPISODE_CODE_RE`, `ARR_DETAIL_RE`)** — Hard.
Feature folders own domain/display transforms. Arr title/detail parsing and dialog view-models should live in `automation-format` / models, not the dashboard board.

**`docs/design/modal-concepts.html`** — Soft/hard-adjacent.
Repo ignores `/docs/mockups/`; this 726-line static concept page is the same class of artifact. Storybook is the design-system showcase—not parallel HTML mockups with localhost poster URLs.

**`angular.json` `anyComponentStyle` 8kB→9kB** — Soft vs budgets guidance.
Looks like relaxing the gate for `automation-card.scss` growth rather than extracting styles.

No AGENTS/`ACTIONS_TOKEN`, Live wiring, or wire-DTO leakage issues found.

### Baseline smells (judgement)

- **Duplicated Code** — Same chrome/body skeleton shape across library, upcoming, downloads, automation; loading opacity rules repeated in `media-ui.scss` and card `:host-context(...)`.
- **Shotgun Surgery** — One loading UX spreads across `dashboard-page`, four cards, `metric-card`, and `media-ui.scss`.
- **Primitive Obsession** — Arr stats / season-episode parsed from strings via regex.
- **Feature Envy** — Board invents dialog groups from `AutomationProblemItem` fields instead of a feature mapper.
- **Speculative Generality** — `DialogItemRow.code` always `''`.
- **Divergent Change** — `automation-card` mixes skeleton loading, service list, and full Sonarr/Radarr dialog redesign.
- **Duplicated Code** — Progress `@keyframes shimmer` vs skeleton `mm-skeleton-shimmer`.
- **ui-ux-design-review.md (Nocturne: no heavy gradients)** — Always-on progress gradient + live shimmer soft-conflicts with flattened surfaces; reduced-motion handling is fine.

---

## Spec

No spec available (reviewer choice).

---

## Summary

Standards ~4 documented + ~8 smell findings; Spec skipped.
Worst Standards issue: page-specific loading chrome living in shared `app/ui` (`media-ui.scss`).
