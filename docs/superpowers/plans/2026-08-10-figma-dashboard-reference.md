# Figma Dashboard Reference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a faithful wide-desktop `91 — Dashboard Reference` page in the existing Media Manager Angular Figma design-system file, matching the current Angular `/` dashboard and Demo-mode data.

**Architecture:** The Angular repository is the layout/content source of truth and the existing Lumen Figma file is the design-system source of truth. Create one 1440px-wide, full-dashboard reference frame using a 228px sidebar, fluid 916px center shell column, and 296px right rail; the center column keeps the production 26px horizontal padding, leaving 864px of dashboard content at this viewport. Reuse existing Figma components and local variables wherever they represent production primitives; assemble production-only composites directly on the reference page with auto-layout rather than creating new public library components.

**Tech Stack:** Angular 22 source templates/SCSS, Lumen `--mm-*` design tokens, Figma Plugin API via `use_figma`, existing Figma components/variants/variables/text styles.

## Global Constraints

- Target Figma file: `CLiBuUebdtiPUohRDBAvaz`.
- Create exactly one new page named `91 — Dashboard Reference` for the first pass.
- This is a reproduction task, not a redesign: do not simplify, restyle, rename, or reorganize product UI.
- Use the normal/ready Demo-mode state, not loading/error/empty states, for the primary frame.
- Use repository Demo fixtures wherever deterministic content exists.
- Preserve CSS-gradient artwork from Demo fixtures; do not substitute unrelated posters/backdrops.
- Use existing Lumen variables and text styles before hardcoded colors/type values.
- Match fixed code dimensions exactly where the Angular SCSS specifies them.
- Use auto-layout for structural containers.
- Do not create new public design-system components unless an existing Angular primitive cannot be represented by the existing Figma component system; production composites belong on the reference page.
- Responsive breakpoint frames are out of scope for this first pass.
- Figma changes are autosaved; repository changes in this plan are limited to spec/plan documentation.

---

## File / Artifact Structure

**Repository source references (read-only):**
- `dashboard-app/projects/dashboard/src/app/app.html` — shell composition, sidebar content, right rail placement.
- `dashboard-app/projects/dashboard/src/app/app.scss` — shell dimensions, sidebar width, main padding, right-rail width, responsive thresholds.
- `dashboard-app/projects/dashboard/src/app/topbar/topbar.ts` — topbar controls and copy.
- `dashboard-app/projects/dashboard/src/app/topbar/topbar.scss` — topbar spacing and search width.
- `dashboard-app/projects/dashboard/src/app/dashboard/dashboard-page/dashboard-page.html` — dashboard section order and rail/download contents.
- `dashboard-app/projects/dashboard/src/app/dashboard/dashboard-page/dashboard-page.scss` — dashboard section spacing and downloads heading/stats layout.
- `dashboard-app/projects/dashboard/src/app/dashboard/dashboard-hero/dashboard-hero.html` — hero hierarchy and actions.
- `dashboard-app/projects/dashboard/src/app/dashboard/dashboard-hero/dashboard-hero.scss` — hero geometry and typography.
- `dashboard-app/projects/dashboard/src/app/dashboard/dashboard-hero/hero.facade.ts` — hero title emphasis/meta formatting.
- `dashboard-app/projects/dashboard/src/app/dashboard/stat-strip/stat-strip.html` — five stat items and icon intent.
- `dashboard-app/projects/dashboard/src/app/dashboard/stat-strip/stat-strip.scss` — stat-strip grid/card geometry.
- `dashboard-app/projects/dashboard/src/app/dashboard/media-rail/media-rail.ts` — rail headings/count/link/arrows.
- `dashboard-app/projects/dashboard/src/app/right-rail/right-rail.html` — upcoming/activity/health composition.
- `dashboard-app/projects/dashboard/src/app/right-rail/right-rail.scss` — right-rail spacing and activity styling.
- `dashboard-app/projects/dashboard/src/app/media-stack/mock-media-stack-api.ts` — deterministic Demo-mode data.

**Figma artifacts:**
- Create page: `91 — Dashboard Reference`.
- Create frame: `Dashboard / Desktop / Ready / 1440`.
- Inside the frame create three shell columns named `Sidebar`, `Main Content`, and `Right Rail`.
- Preserve reusable instances from the existing component pages; do not detach instances unless a production composite cannot be represented otherwise.

---

### Task 1: Freeze Source Truth and Build the Figma Component Map

**Files:**
- Read: all repository source references listed above.
- Inspect Figma pages: `10 — Button`, `12 — Icon Button`, `22 — Search Pill`, `40 — Status`, `41 — Progress`, `43 — State Card`, `61 — Poster`, `70 — Card`, `72 — Upcoming Item`, `73 — Service Row`, `74 — Download Item`, and `90 — Patterns`.
- No Figma mutations in this task.

**Interfaces:**
- Consumes: approved spec `docs/superpowers/specs/2026-08-10-figma-dashboard-reference-design.md`.
- Produces: a runtime component map containing each required Figma component/component-set node ID, usable variants/properties, relevant local variable IDs, and text-style IDs.

- [ ] **Step 1: Read the production source files and record fixed geometry.**

Record these invariants before any Figma mutation:

```text
Shell: 228px sidebar | minmax center | 296px right rail
Main content padding: 20px 26px 60px
Topbar gap: 16px; bottom margin: 22px; search max-width: 520px
Hero: min-height 380px; radius --mm-radius-lg; content max-width 620px; padding 32px 34px 26px
Stat strip: 5 items; gap 14px; margin-top 18px; card padding 15px 18px
Downloads: margin-top 34px; heading gap 14px; header bottom margin 14px
Right rail: padding 22px 18px; section gap 26px
```

- [ ] **Step 2: Read Demo fixtures and resolve the visible ready-state copy.**

Build a deterministic content sheet from `mock-media-stack-api.ts` plus the formatting/selectors used by the dashboard. It must include at minimum:

```text
Hero: The Expanse; Featured; S4 E2 · Jetsam; 2015; ★ 8.3; 45m; Sci-Fi, Adventure; 42% progress
Library: 428 movies; 76 series
Storage: 4.8 TiB of 7.2 TiB
Continue Watching: visible in-progress items after selector/filter logic
Trending: current Demo Trakt items after mapping
Recently Added: first 10 library items after current facade ordering
Downloads: Afterlight, The Blue Hour, Orbit Station with current mapped states/rates/ETA
Right rail: first 4 upcoming events, current activity feed, current sorted service-health rows
```

Do not invent copy if the fixture/formatter provides it.

- [ ] **Step 3: Inspect the existing Figma component pages with read-only `use_figma` calls.**

For each target page, switch to that page once and return:

```js
const page = figma.root.children.find(p => p.name === TARGET_PAGE);
await figma.setCurrentPageAsync(page);
return figma.currentPage
  .query('COMPONENT, COMPONENT_SET')
  .values(['id', 'name', 'type', 'key']);
```

Also inspect sample instances/components for `componentProperties`, dimensions, text properties, and nested-instance structure. Do not mutate the canvas.

- [ ] **Step 4: Inspect variables and text styles needed by the shell/dashboard.**

Resolve local variables for:

```text
surface/page
surface/card
surface/control
border/default
border/divider
text/primary
text/secondary
text/muted
accent/default
accent/strong
status/success
status/warning
status/danger
status/premiere
space/*
radius/*
typography/font/body
typography/font/display
typography/font/mono
```

Resolve text styles for display headings, body, labels, button labels, poster text, status labels, and right-rail headings.

- [ ] **Step 5: Verify the component map covers every production primitive before proceeding.**

Expected coverage:

```text
Button / Button Link
Icon Button
Search Pill
Progress
Status
State Card
Media/Poster card representation
Upcoming Item
Service Row
Download Item
```

If `Media Card` has no exact public Figma component, mark it as a reference-page composite assembled from existing primitives; do not substitute the generic Card if it changes the shipped appearance.

---

### Task 2: Create the Reference Page and Production Shell

**Files:**
- Modify Figma file `CLiBuUebdtiPUohRDBAvaz`.
- Create page `91 — Dashboard Reference`.
- Create frame `Dashboard / Desktop / Ready / 1440`.

**Interfaces:**
- Consumes: component/variable/style map from Task 1.
- Produces: stable page ID and root frame ID used by all later tasks.

- [ ] **Step 1: Create the page only if it does not already exist.**

Use `figma.createPage()` in Design mode. If the page already exists from an interrupted run, reuse it rather than creating `91 — Dashboard Reference 2`.

- [ ] **Step 2: Create the 1440px root frame as the first page child.**

Create an auto-layout horizontal frame:

```text
Name: Dashboard / Desktop / Ready / 1440
Width: 1440
Height: hug contents / final full-dashboard height
Fill: Lumen semantic surface/page
Clip content: true
Gap: 0
```

Return the created page/root IDs.

- [ ] **Step 3: Create the three shell columns directly inside the root.**

```text
Sidebar: fixed 228px width; vertical; top padding 22; horizontal padding 16
Main Content: fill remaining width; vertical; padding 20 top / 26 horizontal / 60 bottom
Right Rail: fixed 296px width; vertical; padding 22 vertical / 18 horizontal
```

Apply the production divider borders between columns using `border/divider`.

- [ ] **Step 4: Build the left sidebar in production order.**

Create/instantiate:

```text
Brand row: M mark + “Media Manager” + Demo badge
Navigation:
  Dashboard (active)
  Library + count badge
  Discover
  Reports
Footer:
  Storage mini-card
  Service-attention status pill when the Demo fixture is degraded
```

Use Lucide-equivalent vectors already present in the Figma icon system where available. Preserve the production 40px nav-row minimum height, 12px internal gap, 10px/12px padding, 11px radius, and active accent treatment.

- [ ] **Step 5: Visually verify shell geometry before adding dashboard content.**

Take a Figma screenshot of the root. Confirm:

```text
228 + 916 + 296 = 1440
Main inner width = 916 - 52 = 864
Sidebar and right rail stretch to the root frame height
No column overlap or horizontal clipping
```

Do not continue until these are correct.

---

### Task 3: Build Topbar, Hero, and Stat Strip

**Files:**
- Modify Figma page `91 — Dashboard Reference` inside the existing `Main Content` column.

**Interfaces:**
- Consumes: root/main-content IDs from Task 2 and component map from Task 1.
- Produces: `Topbar`, `Dashboard Hero`, and `Stat Strip` frame/instance IDs.

- [ ] **Step 1: Build the topbar using existing Search Pill, Icon Button, and Button instances.**

Use exact production content:

```text
Search placeholder: Search movies, shows, people…
Shortcut: Ctrl+K
Rail toggle: panel-right icon
Primary action: Add media, gold, plus icon
```

Geometry:

```text
Topbar horizontal gap 16px
Search fills available space up to 520px
Actions pushed to the right with 12px gap
Bottom margin 22px
```

- [ ] **Step 2: Build the hero as a production composite.**

Create a 100%-width hero with minimum height 380px, production radius/border/shadow, and the Demo gradient backdrop from `The Expanse`. Layer the two production scrims over the gradient.

Inside the hero content column use:

```text
Max width: 620px
Padding: 32px 34px 26px
Kicker: FEATURED + 26px leading rule
Title: “The Expanse” with last word italic/accent according to splitTitleEmphasis()
Metadata: S4 E2 · Jetsam · 2015 · ★ 8.3 · 45m · Sci-Fi, Adventure
Overview: Politics and survival between Earth, Mars, and the Belt.
Actions: Play (gold, small) and Details (ghost, small)
Progress: 42% and formatted remaining-time label
```

Use Fraunces for the display title and existing body/label styles elsewhere.

- [ ] **Step 3: Build the five-item stat strip.**

Use a responsive-looking 5-column row at 864px content width, preserving the production 14px gap and card geometry. Each item contains a 36px icon tile, uppercase label, display value, supporting line, and trailing chevron.

Items in order:

```text
Library
Active downloads
Watch next
Storage
Services
```

Use Demo values from Task 1; do not hardcode guessed totals.

- [ ] **Step 4: Screenshot and compare the upper dashboard.**

Inspect at high enough resolution to verify:

```text
Topbar alignment
Hero 380px minimum height
Hero content left padding and vertical hierarchy
Stat-strip card heights/gaps
No text clipping at 864px main-content width
```

Fix geometry before proceeding.

---

### Task 4: Build the Three Media Rails and Downloads Section

**Files:**
- Modify Figma page `91 — Dashboard Reference` inside `Main Content`.

**Interfaces:**
- Consumes: main-content ID and component map.
- Produces: three rail frames plus a complete ready-state downloads section.

- [ ] **Step 1: Build the shared rail header pattern.**

For each rail use the production anatomy:

```text
Fraunces section title
Optional count/supporting label
Accent link on the right
Two circular small arrow icon buttons
Horizontal content row beneath
```

- [ ] **Step 2: Build Continue Watching.**

Use landscape cards at the shipped width/ratio from the Angular media-card implementation. Populate only entries that survive `progressPercent > 0` and the current rail limit. Preserve gradient artwork, title/subtitle, play cue, and progress indication.

Header:

```text
Continue Watching
<count> in progress
View all →
```

- [ ] **Step 3: Build Trending in Trakt.**

Use poster cards at 158px width for the dashboard rail, matching the current production dashboard override rather than the generic 180px poster-library default.

Header:

```text
Trending in Trakt
This week
Charts →
```

Populate current Demo trending items and rating/subtitle formatting from the repository.

- [ ] **Step 4: Build Recently Added.**

Use the same landscape media-card presentation as production, with the current first-10 ordering and Demo gradient/missing-art treatments.

Header:

```text
Recently Added
Latest arrivals
Library →
```

- [ ] **Step 5: Build Downloads header and summary controls.**

Production anatomy:

```text
Downloads heading
Down rate value + unit
Up rate value + unit
Pause all (quiet)
Resume all (gold)
```

Use the exact Demo summary rates derived from the visible torrent fixtures and current formatting helpers.

- [ ] **Step 6: Populate grouped Download Item instances.**

Use the existing `Download Item` variants and exact Demo torrents:

```text
Afterlight
The Blue Hour
Orbit Station
```

Match grouped state labels, progress, category, downloaded/size labels, down/up rates, ETA/Complete label, pill tone, progress tone, and per-item pause/resume action state.

- [ ] **Step 7: Add the downloads footer link and validate the full center column.**

Footer copy:

```text
Open qBittorrent →
```

Screenshot the full `Main Content` column. Confirm section order exactly matches `dashboard-page.html` and that no horizontal rail/card content bleeds outside the 864px content viewport except where intentionally clipped as a horizontal rail.

---

### Task 5: Build the Right Rail and Run Final Fidelity QA

**Files:**
- Modify Figma page `91 — Dashboard Reference` inside `Right Rail`.
- Read current Demo fixture/formatting source for calendar, activity, and service health.

**Interfaces:**
- Consumes: right-rail ID from Task 2, component map, deterministic Demo content sheet.
- Produces: finished reference frame and final screenshot QA result.

- [ ] **Step 1: Build Upcoming Releases.**

Use `Upcoming Item` instances for the first four current `calendar.events()` entries. Match title/subtitle, formatted air date, `Ready`/scheduled relative label, art gradient, and readiness treatment.

Section header:

```text
Upcoming Releases
View Calendar ›
```

- [ ] **Step 2: Build Recent Activity.**

Use the current Demo activity feed and production row anatomy:

```text
28px state icon tile
12.5px activity title
10.5px subtitle
10.5px relative timestamp aligned right
9px vertical row padding
bottom divider except last row
```

Apply current activity tones: download/premiere, imported/success, deleted/danger, failed/danger.

- [ ] **Step 3: Build Service Health.**

Instantiate `Service Row` variants in the same sorted order as `compareAutomationServices`. Use the exact Demo service names/details/statuses and current label formatting.

Only show the green “All services are running smoothly” panel if the current Demo health evaluates to `allGood() === true`; otherwise omit it, matching production behavior.

- [ ] **Step 4: Make all three shell columns stretch to the final dashboard height.**

Verify sidebar and right-rail backgrounds/dividers reach the bottom of the full dashboard reference, not just the first viewport.

- [ ] **Step 5: Run structural QA with read-only `use_figma`.**

Return and check:

```text
Root width = 1440
Sidebar width = 228
Right Rail width = 296
Main Content width = 916
Main Content horizontal padding = 26 / 26
Hero height >= 380
Exactly 5 stat items
Exactly 3 media rails in production order
Downloads contains all three Demo torrents
Right Rail contains Upcoming Releases, Recent Activity, Service Health
All structural containers use auto-layout
No accidental duplicate `91 — Dashboard Reference` page
```

- [ ] **Step 6: Capture the finished root frame screenshot.**

Use `get_screenshot` with a sufficiently high `maxDimension` to inspect the full dashboard. Check:

```text
Alignment and consistent gutters
Text clipping/overflow
Hero scrim readability
Poster/landscape card proportions
Download row progress and metadata hierarchy
Right-rail density
Sidebar footer placement
No detached/stray nodes outside the root frame
```

- [ ] **Step 7: Correct every visual defect found in the screenshot, then re-capture.**

Do not mark complete until the second screenshot shows no obvious spacing, clipping, hierarchy, or component-state mismatch against the production source.

---

## Final Verification Checklist

- [ ] `91 — Dashboard Reference` exists exactly once.
- [ ] `Dashboard / Desktop / Ready / 1440` is the page's canonical frame.
- [ ] Shell is 228 / 916 / 296 at 1440px.
- [ ] Center dashboard ordering matches `dashboard-page.html` exactly.
- [ ] Hero geometry/copy matches `dashboard-hero.*` and `hero.facade.ts`.
- [ ] Stat strip has five production items and current Demo values.
- [ ] Rails use current Demo data and production card dimensions.
- [ ] Downloads match current Demo fixtures and production formatting.
- [ ] Sidebar/topbar/right rail match the current shell templates and SCSS.
- [ ] Existing Figma variables/styles/components are reused wherever accurate.
- [ ] No placeholder text remains where deterministic Demo content exists.
- [ ] Final high-resolution screenshot has been visually reviewed after the last mutation.
