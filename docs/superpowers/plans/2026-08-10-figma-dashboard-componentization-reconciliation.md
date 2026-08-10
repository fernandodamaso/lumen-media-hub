# Figma Dashboard Componentization Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile the Figma design system and `91 — Dashboard Reference` so the dashboard is assembled from canonical reusable Figma components/application composites wherever the Angular product has a corresponding reusable contract, with no avoidable detached instances, duplicated primitives, or literal stand-ins for existing icons/components.

**Architecture:** Fix canonical design-system dependencies first (`Progress`, `Media Card`, `Upcoming Item`, `Service Row`, `Download Item`). Then add the missing application-level composites and private helper components needed by the dashboard (`Stat Strip`, `Media Rail`, `Right Rail / Activity Row`, `Topbar / Dashboard Hero`, sidebar navigation). Only after those dependencies are correct should `91 — Dashboard Reference` be rebuilt from instances and validated. Angular source and Storybook remain the product contract; Figma represents that contract without inventing APIs.

**Tech Stack:** Angular 22 source/templates/SCSS, Storybook 10, Figma components/component properties/variables/auto-layout, Linear issue hierarchy, GitHub implementation-plan documentation.

## Global Constraints

- Target Figma file: `CLiBuUebdtiPUohRDBAvaz`.
- Angular production code is authoritative for component existence, public inputs, state semantics, responsive behavior, icons, and composition.
- Preserve the current dashboard visual fidelity while improving structure; this is not a redesign.
- Reuse an existing canonical Figma component whenever it accurately represents production.
- Do not create a second public component for an existing Angular component; fix the canonical Figma mapping instead.
- Distinguish three Figma asset classes explicitly:
  - **Public component:** maps to an exported/shared Angular UI component.
  - **Application composite:** maps to a shipped application component such as `DashboardHero`, `StatStrip`, `MediaRail`, `Topbar`, `RightRail`, `UpcomingItem`, `ServiceRow`, or `DownloadItem`.
  - **Private helper:** Figma-only reusable construction helper for repeated internal anatomy such as a stat card, nav item, or activity row. Private helpers must not be presented as public Angular APIs.
- Do not detach an instance to work around a deficient canonical component. Fix the canonical component or document a genuine Figma-platform exception.
- Do not use literal text glyphs (`×`, `›`, pseudo-icons) where a canonical icon component exists.
- Keep component variant matrices bounded; avoid enumerating arbitrary numeric values as production API variants.
- Do not mask canonical mismatches with local dashboard overrides unless the Angular source has a real contextual override.
- Use semantic variables for canonical colors, spacing, radii, and component dimensions where matching variables exist.
- Code Connect remains blocked by the current Figma plan/seat and is non-blocking.

---

## Baseline Audit — 2026-08-10

Current `91 — Dashboard Reference` structural audit:

```text
Frames inside dashboard: 231
Reusable instances: 37
Component definitions inside dashboard: 0
```

Confirmed avoidable/manual structures:

```text
5  hand-built dashboard stat cards
6  hand-built media-rail arrow buttons
10 hand-built media cards
6  hand-built activity rows
6  hand-built activity icon tiles
4  hand-built sidebar nav items
3  detached/custom Download Item rows
6+ hand-built progress visuals, plus hero/sidebar progress
3  repeated media-rail header/navigation structures
```

Known examples reported by review:

```text
395:45  Stat / Library          -> should be reusable Stat Card/Stat Strip structure
396:25  Rail Arrow              -> should be canonical Icon Button + chevron icon
396:44  Night Transit / Info    -> should come from canonical MmMediaCard landscape instance
397:207 Activity Icon           -> should use shared Lucide/icon component inside reusable Activity Row
```

## Target Structural Acceptance

After reconciliation:

```text
0 avoidable detached instances in Dashboard Reference
0 hand-built rail arrow controls
0 literal text glyphs used as icons when canonical icon components exist
5 stat cards are instances of one private Stat Card helper inside a StatStrip application composite
4 sidebar nav entries are instances of one private Nav Item helper
6 activity entries are instances of one private Activity Row helper
10 dashboard media cards are canonical MmMediaCard instances
3 download rows are canonical Download Item instances, except only if a documented Figma numeric-value limitation makes exact progress impossible without an explicit reference-only strategy
3 media rails use one MediaRail application-composite contract
Topbar, DashboardHero, StatStrip, MediaRail, and RightRail are represented as application composites rather than anonymous repeated frames
Every intentional non-instance exception is documented in `98 — QA & Sandbox`
```

---

## Phase 1 — Fix Canonical Dependencies First

### Task 1: FDM-581 — Reconcile Progress for production use

**Linear:** existing `FDM-581 — P3.L — Reconcile status and feedback components in Figma`

**Source:**
- `dashboard-app/projects/dashboard/src/app/ui/progress.*`
- Storybook Progress stories
- Dashboard uses in hero/media cards/downloads/sidebar storage

**Problem:** The Figma `Progress` set currently models discrete `Value=0|25|50|75|100` variants, while Angular accepts arbitrary numeric values. That limitation caused dashboard progress to be redrawn manually and contributed to detached Download Item instances.

- [ ] Inspect the exact Angular `MmProgress` public inputs and rendered geometry.
- [ ] Keep the canonical public component API honest: do not pretend arbitrary numeric values are a finite variant enumeration.
- [ ] Determine and implement the best Figma representation for arbitrary-value reference geometry without detaching consumers. Preferred order:
  1. reusable nested/helper strategy that lets exact reference fills remain instances;
  2. reference-only exact-value helper variants clearly labeled as samples, not production API enumeration;
  3. if Figma cannot represent arbitrary numeric geometry through component properties, document that platform limitation and define the smallest controlled contextual exception.
- [ ] Reconcile `showLabel`, tone, shimmer/loading behavior, track/fill height, colors, and accessibility documentation from source.
- [ ] Add screenshot examples including non-quarter production values (`6`, `18`, `31`, `42`, `68`, `100`) so the dashboard use case is explicitly tested.
- [ ] Acceptance: no future dashboard consumer needs to detach a Progress-containing component solely to display `31%` or `68%` without an explicitly documented Figma limitation.

### Task 2: FDM-583 — Make MmMediaCard the canonical dashboard media component

**Linear:** existing `FDM-583 — P3.N — Reconcile Media Card and retire Poster as canonical mapping`

- [ ] Reconcile canonical `MmMediaCard` from current source, including `layout=portrait|landscape`, caption placement, framing, title/subtitle, rating, episode, tag, progress, showPlayCue, art/image behavior, and link semantics.
- [ ] Ensure the landscape instance reproduces dashboard width/ratio/contextual behavior (`272px`, `16/10`) without rebuilding internal title/subtitle/progress anatomy locally.
- [ ] Ensure portrait instances support the dashboard's `158px` contextual width without detaching the component.
- [ ] Preserve `Poster` only as deprecated migration evidence, not the canonical production component.
- [ ] Acceptance: all 10 dashboard media-card occurrences can be represented as `MmMediaCard` instances; nodes such as `396:44 Night Transit / Info` disappear as hand-built card internals.

### Task 3: FDM-586 — Reconcile Upcoming Item application composite

**Linear:** existing `FDM-586 — P3.Q — Reconcile Upcoming Item application composite in Figma`

- [ ] Reconcile title, subtitle, art, air-date, ready/scheduled treatment, link behavior, and current dimensions against source.
- [ ] Keep it classified as an application composite rather than a shared UI primitive.
- [ ] Verify the four dashboard right-rail occurrences remain component instances after updates.

### Task 4: FDM-587 — Reconcile Service Row application composite

**Linear:** existing `FDM-587 — P3.R — Update Service Row branding and status presentation in Figma`

- [ ] Match current service icon + initial fallback behavior.
- [ ] Match healthy/degraded/down/unknown treatment and current detail/status text.
- [ ] Remove stale Figma-only tile treatments not present in source.
- [ ] Verify all eight dashboard service rows remain instances with no local patch frames.

### Task 5: FDM-588 — Reconcile Download Item without detachment

**Linear:** existing `FDM-588 — P3.S — Reconcile Download Item composite in Figma`

- [ ] Reconcile the current Angular Download Item state/action/metadata contract.
- [ ] Integrate the Progress strategy from FDM-581 rather than embedding an incompatible fixed 50% visual.
- [ ] Preserve action Icon Button instances, category metadata, state pill, rates, ETA, and responsive behavior.
- [ ] Provide exact dashboard examples for Afterlight `68%`, The Blue Hour `31%`, and Orbit Station `100%`.
- [ ] Acceptance: the three dashboard download rows remain `Download Item` instances; no detach is used to reach exact production values unless the FDM-581 limitation is explicitly documented and approved.

---

## Phase 2 — Add Missing Application Composites and Private Helpers

### Task 6: New Linear issue — Componentize Stat Strip and private Stat Card helper

**Angular contract:** `dashboard/stat-strip/*`

- [ ] Create a private `_Internal / Dashboard / Stat Card` helper representing icon tile, uppercase label, Fraunces value, supporting text, optional tone, and trailing chevron.
- [ ] Expose text/icon/tone through component properties; do not make five separate components.
- [ ] Use canonical shared icon components rather than copied SVG/vector/text icons.
- [ ] Create `Application / Dashboard / Stat Strip` matching the shipped `StatStrip` layout and wrap behavior.
- [ ] Replace all five hand-built dashboard stat cards with instances.
- [ ] Acceptance: `395:45`, `395:57`, `395:68`, `395:77`, `395:88` are no longer standalone hand-built frames.

### Task 7: New Linear issue — Componentize sidebar navigation anatomy

**Angular contract:** sidebar portion of `app.html` / `app.scss`

- [ ] Create private `_Internal / Shell / Nav Item` with `active/default`, icon swap, label text, and optional badge/count.
- [ ] Use canonical icon components for Dashboard, Library, Discover, Reports.
- [ ] Preserve production 40px minimum height, gap, padding, radius, active accent treatment, and optional trailing badge.
- [ ] Replace the four hand-built nav rows with instances.
- [ ] Keep `Sidebar` itself a page/shell composition unless a reusable shipped Angular component emerges; do not invent a public Angular `Sidebar` API.

### Task 8: New Linear issue — Create Media Rail application composite using canonical controls/cards

**Angular contract:** `dashboard/media-rail/*`

- [ ] Create `Application / Dashboard / Media Rail` mapped to the shipped `MediaRail` component.
- [ ] Model title, count/supporting text, link label, and child-content slot/pattern without variant explosion.
- [ ] Replace all six hand-built `Rail Arrow` frames with canonical `Icon Button` instances using small/circle + Chevron Left/Right icon swaps.
- [ ] Define the contextual rail gap, header margin, nav gap, clipping/overflow annotation, and hover headroom from source.
- [ ] Rebuild Continue Watching, Trending in Trakt, and Recently Added rails using this application composite + canonical `MmMediaCard` instances.
- [ ] Acceptance: nodes `396:23`, `396:25`, `396:56`, `396:58`, `396:88`, `396:90` are Icon Button instances; no rail header/nav is independently redrawn.

### Task 9: New Linear issue — Create Right Rail application composite and private Activity Row helper

**Angular contract:** `right-rail/*`

- [ ] Create private `_Internal / Right Rail / Activity Row` with icon swap/tone, title, subtitle, timestamp, link/no-link presentation, and divider behavior.
- [ ] Use the canonical icon library for Download, CircleCheck, Trash2, and CircleAlert; remove literal `×` or arrow glyph stand-ins.
- [ ] Create `Application / Right Rail` using canonical `Upcoming Item`, Activity Row, and `Service Row` instances.
- [ ] Preserve production section gaps, heading/link styles, row density, and all-good conditional composition.
- [ ] Replace all six hand-built activity rows/icons with instances.
- [ ] Acceptance: `397:171`–`397:213` repeated activity anatomy is instance-driven; `397:207` no longer contains a literal `×` icon.

### Task 10: New Linear issue — Create Topbar and Dashboard Hero application composites

**Angular contracts:** `topbar/*`, `dashboard/dashboard-hero/*`

- [ ] Create `Application / Topbar` from Search Pill, Icon Button, and Button instances.
- [ ] Create `Application / Dashboard Hero` from canonical Button/Button Link/Progress/icon instances plus source-backed hero typography and scrim geometry.
- [ ] Expose only meaningful Figma properties needed to compose reference states; do not model data/business logic as variants.
- [ ] Preserve contextual widths, spacing, title emphasis, button variants/icons, and progress placement.
- [ ] Replace anonymous Topbar/Hero frames on the dashboard with instances of these application composites.

---

## Phase 3 — Rebuild `91 — Dashboard Reference` From Canonical Assets

### Task 11: New Linear issue — Migrate Dashboard Reference to canonical instances

**Blocked by:** FDM-581, FDM-583, FDM-586, FDM-587, FDM-588, and Tasks 6–10.

- [ ] Rebuild the canonical desktop dashboard frame from the corrected components/application composites/private helpers.
- [ ] Keep only legitimate page-level layout frames: root shell columns, main vertical page flow, and contextual wrappers that do not map to reusable production/UI anatomy.
- [ ] Replace all known hand-built duplicates from the baseline audit.
- [ ] Remove detached Download Item remnants and old manual Media Card/rail/stat/activity/nav frames.
- [ ] Preserve exact Demo content and current source-defined dimensions.
- [ ] Run a dashboard subtree audit and inventory every remaining `FRAME` that visually resembles a reusable control/component.
- [ ] For each remaining manual frame, classify it explicitly as:
  - legitimate one-off page layout,
  - contextual exception documented in QA,
  - or defect requiring another component conversion.
- [ ] Acceptance: target structural metrics from this plan pass; no avoidable duplicate primitive remains.

---

## Phase 4 — Patterns, Responsive References, and Final QA

### Task 12: FDM-589 — Expand Patterns and responsive/state reference compositions

**Linear:** existing `FDM-589 — Phase 4 — Build Patterns and Dashboard Reference compositions in Figma`

After Task 11 has converted the canonical dashboard:

- [ ] Build/refresh `90 — Patterns` from the new canonical instances: media rail, service-health list, download list, right rail, state handling.
- [ ] Add/validate responsive dashboard references from real 1240/900/560 source behavior; preserve the issue's approved mobile/desktop reference requirement.
- [ ] Ensure patterns never duplicate component internals merely for convenience.
- [ ] Record intentional contextual overrides separately from canonical component behavior.

### Task 13: FDM-590 — Final structural/visual/contract QA

**Linear:** existing `FDM-590 — Phase 5 — Run final Figma QA, approval gate, publication, and Code Connect check`

Add dashboard-specific acceptance to the existing final audit:

```text
0 avoidable detached dashboard instances
0 manual rail arrows
0 literal text icons where canonical icons exist
5/5 stat cards componentized
4/4 nav items componentized
6/6 activity rows componentized
10/10 dashboard media cards canonical MmMediaCard instances
3/3 download rows canonical Download Item instances or one explicitly documented Figma-platform exception strategy
3/3 media rails application-composite driven
Topbar, DashboardHero, StatStrip, MediaRail, RightRail represented as application composites
```

- [ ] Run metadata/component-property validation on every new/modified component set.
- [ ] Screenshot the canonical dashboard and relevant component/pattern pages.
- [ ] Run structural scan for duplicated manual primitives, default layer names, detached instances, hardcoded canonical values, and literal glyph icons.
- [ ] Record all genuine Figma-platform limitations in `98 — QA & Sandbox` rather than hiding them.
- [ ] Stop at the existing explicit approval gate before publication.

---

## Dependency Order

```text
FDM-581 Progress ─────────┬─> FDM-583 Media Card ─────────────┐
                         └─> FDM-588 Download Item ──────────┤
FDM-586 Upcoming Item ───────────────────────────────────────┤
FDM-587 Service Row ─────────────────────────────────────────┤
New: Stat Strip / Stat Card ─────────────────────────────────┤
New: Sidebar Nav Item ───────────────────────────────────────┤
New: Media Rail ─────────────────────────────────────────────┤
New: Right Rail / Activity Row ──────────────────────────────┤
New: Topbar / Dashboard Hero ────────────────────────────────┤
                                                            v
                                      New: Dashboard instance migration
                                                            |
                                                            v
                                       FDM-589 Patterns/responsive refs
                                                            |
                                                            v
                                            FDM-590 Final QA/approval
```

## Issue Management Rules

- Reuse and refine `FDM-581`, `FDM-583`, `FDM-586`, `FDM-587`, `FDM-588`, `FDM-589`, and `FDM-590`; do not create duplicates.
- Create five missing componentization/application-composite issues plus one dashboard-migration issue.
- Keep all issues in `Media Manager - Angular`, team `Fdmaso`, under the existing Figma reconciliation initiative/parent structure (`FDM-577`).
- Link the new issues to `FDM-589` as the Phase 4 dashboard/pattern umbrella.
- Make the dashboard-migration issue blocked by every canonical/componentization dependency.
- Make `FDM-589` blocked by the dashboard-migration issue.
- Make `FDM-590` blocked by `FDM-589`.
- Use `design` plus an appropriate complexity label; add `ready-for-agent` only when scope/dependencies are concrete.

## Plan Self-Review

- Spec coverage: baseline audit, existing canonical component debt, missing helpers/application composites, dashboard migration, patterns, responsive states, and final QA are all assigned to explicit tasks.
- Placeholder scan: no TBD/TODO placeholders remain.
- Scope check: Angular production code is read-only for this effort; all implementation changes target Figma plus planning/issue metadata.
- Ambiguity check: public components, application composites, private helpers, and legitimate page layout are explicitly distinguished to prevent over-componentizing every frame.
