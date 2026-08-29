# Media Manager Angular

Angular 22 workspace for the Media Manager shell: a single `dashboard` app with local design system (`app/ui`) and API boundary (`app/media-stack`). Containerized with Nginx reverse proxy for Docker deployment.

## Quick start (Demo / mock)

```bash
npm ci
npm start
```

Open [http://localhost:4200/](http://localhost:4200/). Default startup uses in-process mock data (**Demo** badge) and makes no private API calls.

| Route | Surface |
|-------|---------|
| `/` | Lumen home: dashboard hero, stat strip, Continue Watching, Newly Available, Trending in Trakt, downloads, and shell rails |
| `/library` | Library poster grid with movie/series filtering |
| `/reports` | Status-weighted automation / cron triage |
| `/discover` | Hermes, Jellyseerr, and Trakt recommendations with lifecycle-aware Jellyseerr requests |
| Storybook | Design-system showcase - `npm run storybook` -> [http://localhost:6006/](http://localhost:6006/) |

## Stack and Live development

This README stays frontend-focused. Install, Compose, production deployment, Live development, proxying, and token-security details live in the [root README](../README.md).

## Scripts

| Script | Purpose |
|--------|---------|
| `npm start` | Demo serve (`:4200`) |
| `npm run start:live` | Live serve with API proxy (**dev-container only**; used by `docker-compose.dev.yml`) |
| `npm run lint` | Rigorous ESLint (typed + strict, used by `quality` gate) |
| `npm run lint:fast` | Fast ESLint (day-to-day editing, used by `lint:agent`) |
| `npm run lint:fix` | Rigorous ESLint with auto-fix |
| `npm run lint:styles:fix` | Stylelint with auto-fix |
| `npm run quality` | **Full gate** — lint + typecheck + styles + duplicates + dead-code + architecture in parallel |
| `npm test -- --watch=false` | Vitest unit / facade / page specs |
| `npm run test:smoke` | Playwright direct-route and assembled-app smoke checks (auto-starts dev server) |
| `npm run build` | Canonical production (Demo mode) build |
| `npm run build:live` | Production-live Docker build (optimized, no source maps, live backend) |
| `npm run storybook` | Interactive Storybook (includes a11y addon / play functions) |
| `npm run build:storybook` | Compile Storybook static output |
| `npm run test:storybook` | Serve `storybook-static` and run interaction/a11y checks (`@storybook/test-runner`) |

## Quality gate

`npm run quality` runs all six checks in parallel via `concurrently`:

| Tool | Command | Exit | Expected |
|------|---------|------|----------|
| **ESLint** (typed + strict) | `npm run lint` | **FAIL** on errors | Auto-fix with `npm run lint:fix` |
| **TypeScript** | `npm run typecheck` | **FAIL** on errors | Fix type errors |
| **Stylelint** | `npm run lint:styles` | **FAIL** on errors | Auto-fix with `npm run lint:styles:fix` |
| **jscpd** (duplication) | `npm run quality:duplicates` | **FAIL** ≥3% | Refactor — do not add ignores |
| **Knip** (dead code) | `npm run quality:dead-code` | **FAIL** on unused | Remove or justify exports |
| **Dependency Cruiser** | `npm run quality:architecture` | **FAIL** on violations | Respect module boundaries |

**PASS** = zero exit. **WARN / INFO** = tool-specific warnings that do not block. **FAIL** = non-zero exit.

**Rules:**
- Do not add ignore comments or abstractions solely to silence the gate.
- Ponytail (lazy/simplification mindset) remains a review principle for agents, not a lint rule.
- `no-orphans` is removed from Dependency Cruiser; Knip owns unused-code detection.
- jscpd clones below 3% are informational — address during refactors.

All six checks run independently: one failure does not kill the others. Commit hook and CI both enforce `npm run quality`. Tests and build run after quality in CI.

## Appearance

Single dark theme — **Lumen** (gold/violet on near-black). Fonts (Fraunces, Inter, and JetBrains Mono) are self-hosted via Fontsource. There is no user theme selection or persisted theme state.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the port -> adapter -> facade -> page flow, Demo/Live modes, and operational link policy.

The command palette is the global movie/show search surface in both modes. It shows local library matches immediately, then uses the shared `MediaStackApi` search/request contracts for authoritative lifecycle groups, TV season selection, and degraded catalog messaging. Demo uses deterministic fixtures; Live keeps Jellyseerr and service credentials behind the same-origin backend proxy.

## Testing

- **Unit / integration:** Vitest via `ng test` (facades, boards, pages, shell navigation, API boundary).
- **Storybook:** Interactive review via `npm run storybook`. CI runs `build:storybook` then `test:storybook` (play functions + a11y).
- **Browser acceptance:** Playwright verifies direct routes, fallback routing, titles, the Lumen palette, responsive shell navigation, and the 390px, 1440px, and 1600px layouts via `npm run test:smoke`. Loading / empty / failure isolation that cannot be selected in Demo UI is covered by the named unit specs beside each feature.

## Non-goals

- Published to npm/hosting (private self-hosted Docker deployment)
- Backend rewrite or secrets in this repo

## Verification

```bash
npm ci
npm start
# in another shell:
npm run quality
npm test -- --watch=false
npm run test:smoke
npm run build
npm run build:storybook
npm run test:storybook
```
