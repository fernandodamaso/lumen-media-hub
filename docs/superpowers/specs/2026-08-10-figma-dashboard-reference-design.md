# Figma Dashboard Reference Design

Date: 2026-08-10
Status: Approved for implementation
Target: `91 — Dashboard Reference` in the Media Manager Angular Figma design-system file
Source repository: `fernandodamaso/lumen-media-hub`

## Goal

Create a faithful Figma reproduction of the current Angular `/` dashboard. The Angular implementation is the behavioral/layout source of truth; the existing Lumen Figma variables, styles, and component pages are the visual-system source of truth.

This is a reproduction task, not a redesign. Do not simplify, restyle, rename, or reorganize product UI unless the production code already does so.

## Primary reference

Build one production-reference desktop frame on a new Figma page named `91 — Dashboard Reference`.

The frame must reproduce the current application shell:

- 228 px fixed left sidebar.
- Fluid center content column.
- 296 px right rail when open.
- Page background, borders, typography, radii, and semantic colors mapped to existing Lumen variables/styles.
- Main content padding and spacing taken from the current Angular SCSS.

The frame should be tall enough to show the complete dashboard vertically rather than cropping after the first viewport.

## Dashboard composition

Reproduce the production order exactly:

1. Topbar inside the main content column.
2. Dashboard hero.
3. Five-item stat strip.
4. Continue Watching media rail.
5. Trending in Trakt poster rail.
6. Recently Added media rail.
7. Downloads section with summary rates, global actions, grouped torrent states, progress, metadata, per-item actions, and footer link.
8. Persistent left sidebar content including brand, navigation, library count, storage summary, and service-attention status.
9. Persistent right rail content from the production shell.

## Production demo content

Use the repository's Demo-mode fixture content wherever a deterministic value exists. Examples include:

- Hero: The Expanse, featured treatment, S4 E2 metadata, 42% progress.
- Library stats: 428 movies and 76 series.
- Continue Watching: The Expanse and Dune as in-progress items, plus any other production-visible entries implied by the current selector/filter logic.
- Recent library items: Dune, Afterlight, Orbit Station, Night Transit, Cowboy Bebop, The Expanse, The Blue Hour, Broken Signal, constrained by the dashboard rail limit.
- Downloads: Afterlight, The Blue Hour, Orbit Station with the exact demo progress/rate/state mappings.
- Storage: 4.8 TiB used of 7.2 TiB.
- Service health and calendar/activity content: use the current demo fixtures and formatting logic.

Where the demo API intentionally uses CSS gradients instead of image assets, reproduce those gradients rather than substituting unrelated artwork.

## Fidelity rules

- Match exact production dimensions where the code uses fixed values.
- Match code-defined gaps, paddings, min-heights, radii, and typography sizes.
- Match semantic state colors through existing Figma variables whenever available.
- Reuse existing Figma components/variants when they represent the Angular primitive accurately.
- If a production composite has no existing public Figma component, assemble it from existing primitives and frames on the reference page instead of inventing a new visual design.
- Preserve content hierarchy, labels, button variants, icon intent, alignment, and visible states.
- Use auto-layout for structural containers.
- Use the current normal/ready desktop state, not loading/error/empty states, for the primary dashboard frame.

## Responsive scope

The first implementation is the canonical wide desktop reference. Responsive breakpoints remain documented by the Angular implementation but are not required as separate frames in this first pass. They can be added after the desktop frame is visually validated.

## Validation

Before completion:

- Compare shell column widths against `app.scss`.
- Compare dashboard section ordering against `dashboard-page.html`.
- Compare hero geometry and typography against `dashboard-hero.scss`.
- Compare stat-strip sizing against `stat-strip.scss`.
- Verify existing component instances against their component-page variants.
- Capture a Figma screenshot of the finished reference frame and visually inspect alignment, clipping, spacing, and hierarchy.
- Do not mark complete if the reference page contains placeholder copy where deterministic demo content exists in the repository.
