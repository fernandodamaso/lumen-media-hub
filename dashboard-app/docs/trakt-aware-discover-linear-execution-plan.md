# Linear Execution Plan — Trakt-Aware Discover Filtering

## Publication target

- Team: `Fdmaso`
- Project: `Media Manager - Angular`
- State: `Ready`
- Priority: `High`
- Assignee, cycle, due date, and estimate: unset
- Structure: one parent issue and seven executable child issues
- Execution: local-only in `D:\media`, sequential where dependencies exist
- Publication order: parent → 1 → 2 → 3 → 4 → 5 → 6 → 7
- Publication status: approved and publication-ready, but not yet created in Linear

When publishing, replace title-based blockers below with the identifiers returned by Linear and set every child’s `parentId` to the new parent identifier.

---

## Parent issue

### EPIC — Keep owned and watched titles out of Discover

**Labels:** `Feature`, `contracts`, `backend`, `frontend`, `testing`, `codex-refined`, `complexity:large`

#### What to build

Make Discover Active a reliable source of unwatched, unowned recommendations:

- Hide movies and shows already playable in Jellyfin.
- Hide movies watched on Trakt.
- Hide a show when at least one episode is watched on Trakt.
- Apply the rules to Hermes, Jellyseerr, and Trakt.
- Preserve excluded Hermes cards in History.
- Prevent later Hermes generations from restoring excluded titles.
- Repair the existing expired Trakt connection with renewable local OAuth tokens.
- Use cached exclusion data with explicit warnings during temporary failures.

All credentials, tokens, and watched-state data stay local. Do not add a dashboard authentication/settings feature.

#### Browser privacy and generation snapshot contract

- The public dashboard `GET /discover/hermes` returns only browser-safe recommendation/history fields, request state, and exclusion freshness (`fresh`, `stale`, or `unavailable`) plus a sanitized warning when needed.
- The public response must not include `revision`, `presented_media_ids`, `context`, `required_retain`, taste data, or typed Arr/Jellyfin/Trakt identity sets. These are generation-control data, not dashboard data.
- Hermes reads those generation-control fields from the authenticated direct host route `http://localhost:8085/internal/discover/hermes` with `X-Actions-Token` and an approved `Origin`. The browser reads `/api/discover/hermes`; browser `/api/internal/*` returns **404**, and direct internal access without the token returns **401**.
- Reconnect, stale-cache, and unavailable errors must be safe for browser-facing responses and logs: no token, secret, raw watched-history record, or unbounded identity dump. A stale snapshot may continue filtering; an unavailable snapshot must state that watched filtering is unavailable and follow the approved fail-open behavior.

References: [Trakt authentication](https://docs.trakt.tv/docs/authentication-oauth), [token exchange](https://docs.trakt.tv/reference/postoauthtoken), and [watched pagination guidance](https://roadmap.trakt.tv/changelog).

#### Acceptance criteria

- [ ] Jellyfin-owned titles never appear in any Active Discover source.
- [ ] Fresh or stale watched snapshots guarantee that Trakt-watched titles never appear in any Active Discover source; unavailable or no-cache results may remain fail-open but require an explicit warning that watched filtering is unavailable.
- [ ] Hermes History retains automatically excluded records.
- [ ] The Trakt connection refreshes without repeated manual token replacement.
- [ ] Temporary source failures use cached exclusions and show a warning.
- [ ] Full backend, Angular, Compose, and live-browser verification passes.
- [ ] No credential or raw watch-history record reaches Angular, logs, Git, or browser responses.

#### Execution constraints

- Work only in the current local checkout.
- Preserve all pre-existing dirty Angular changes.
- Use composite identity `movie:<tmdb_id>` or `tv:<tmdb_id>`.
- Keep Python standard-library-only.
- Use red-green focused tests in every implementation issue.
- Do not stage, commit, push, or broaden scope unless separately requested.

---

## Issue 1 — Hide Jellyfin library titles from Discover Active

**Blocked by:** None — can start immediately<br>
**Labels:** `Bug`, `backend`, `frontend`, `contracts`, `testing`, `codex-refined`, `ready-for-agent`, `complexity:medium`

### What to build

Turn the existing Jellyfin-to-TMDB library map into an authoritative Active-result exclusion. Apply it consistently to Hermes, Jellyseerr, and Trakt without title matching.

Hermes records must remain available in History with an `in_library` exclusion reason.

### Execution checklist

- [ ] Capture `git status --short` and scoped diffs for all currently dirty Discover and shared-card files.
- [ ] Add failing backend tests for movie/TV composite identity and filtering across the three source handlers.
- [ ] Introduce a focused exclusion snapshot abstraction seeded from the existing playable Jellyfin TMDB maps.
- [ ] Return library freshness as `fresh`, `stale`, or `unavailable`, including the last successful refresh time.
- [ ] Filter Jellyseerr and Trakt response items before serialization.
- [ ] Project matching Hermes rows with `excluded_reason: "in_library"` without mutating the store during GET.
- [ ] Add failing Angular tests proving excluded Hermes items leave Active and remain in History.
- [ ] Extend Discover wire models and mappers with the library exclusion state and reason.
- [ ] Show “In library” on the preserved Hermes History card.
- [ ] Re-run focused backend and Angular tests.
- [ ] Review the scoped diff against the captured dirty baseline.

### Acceptance criteria

- [ ] “The Bear” no longer appears in Hermes Active.
- [ ] “The Bear” remains in Hermes History with “In library.”
- [ ] Matching Jellyseerr and Trakt cards are removed.
- [ ] Movie and TV items sharing a numeric TMDB ID do not collide.
- [ ] Jellyfin failure keeps a last-good map when available and reports stale state.
- [ ] No title/year fallback matching is introduced.
- [ ] Existing feedback and request behavior remains unchanged.

### Verification

From `config/homepage-actions`:

```powershell
python -m unittest -v test_discover_exclusions
python -m unittest -v test_generations_api
```

From `dashboard-app`:

```powershell
rtk npx ng test dashboard --watch=false --include=projects/dashboard/src/app/discover/discover-format.spec.ts --include=projects/dashboard/src/app/discover/discover.facade.spec.ts --include=projects/dashboard/src/app/discover/discover-page.spec.ts
```

### Stop conditions

- Stop if implementing the filter requires overwriting unrelated dirty UI work.
- Stop and report a data-contract gap if Jellyfin supplies no TMDB identity; do not compensate with title matching.

---

## Issue 2 — Keep the existing Trakt connection renewable

**Blocked by:** None — can start immediately<br>
**Labels:** `Bug`, `backend`, `testing`, `codex-refined`, `ready-for-agent`, `complexity:medium`

### What to build

Replace the fixed access-token helper with a local OAuth client that securely persists and rotates Trakt access and refresh tokens. Add a one-time PowerShell device-authorization mode that reuses the existing Trakt application.

### Execution checklist

- [ ] Add failing tests for loading, validating, and atomically replacing Trakt token state.
- [ ] Add failing tests for proactive refresh, one retry after `401`, refresh failure, and concurrent refresh requests.
- [ ] Implement a dedicated Trakt client with injected HTTP transport, clock, and token-state path.
- [ ] Refresh when fewer than 60 seconds remain before access-token expiry.
- [ ] Guard refresh with a lock so concurrent requests cannot reuse the same single-use refresh token.
- [ ] Persist both replacement tokens before releasing the refresh lock.
- [ ] Retry the original API request once after a successful refresh; never loop.
- [ ] Add a writable ignored host state directory mounted at `/state`.
- [ ] Keep the backend application mount read-only.
- [ ] Add `TRAKT_CLIENT_SECRET` and token-path configuration while retaining `TRAKT_ACCESS_TOKEN` only as a migration fallback during Issue 2.
- [ ] Add `install.ps1 -Mode connect-trakt`.
- [ ] Implement device-code polling with pending, slowdown, denial, expiry, and success handling.
- [ ] Ensure failed authorization does not overwrite prior valid token state.
- [ ] Ensure no token value is printed.
- [ ] Complete the one-time local authorization with the user.
- [ ] Recreate `homepage-actions` and confirm the Trakt recommendations endpoint returns `200`.

### Acceptance criteria

- [ ] Access and refresh tokens persist in an ignored local state file.
- [ ] A refresh atomically replaces both tokens.
- [ ] Concurrent requests perform no more than one refresh.
- [ ] A `401` causes one refresh and one retry.
- [ ] Invalid refresh state produces a safe reconnect error without secrets.
- [ ] `.\install.ps1 -Mode connect-trakt` successfully reconnects the existing Trakt application.
- [ ] The Trakt tab works after service recreation.

### Verification

From `config/homepage-actions`:

```powershell
python -m unittest -v test_trakt_client
```

From the repository root:

```powershell
pwsh -NoProfile -Command "[void][scriptblock]::Create((Get-Content -Raw .\install.ps1))"
docker compose config
.\install.ps1 -Mode connect-trakt
docker compose --profile requests up -d --force-recreate homepage-actions
Invoke-WebRequest 'http://127.0.0.1:3000/api/discover/trakt?type=shows' -UseBasicParsing
```

### Stop conditions

- Pause at the Trakt verification page for the user to authenticate.
- Never request that the user paste the client secret or token into chat.
- Stop if Compose would expose the state directory through the dashboard or another service.

---

## Issue 3 — Filter watched titles from Trakt recommendations

**Blocked by:** Issue 2<br>
**Labels:** `Feature`, `backend`, `frontend`, `contracts`, `testing`, `codex-refined`, `ready-for-agent`, `complexity:medium`

### What to build

Fetch the authenticated user’s complete watched movie and show identities, cache them locally, and remove matching titles from Trakt recommendations.

A show is considered watched when at least one episode appears in Trakt watched history.

### Execution checklist

- [ ] Add failing parser tests for watched movies, watched shows, missing TMDB IDs, duplicates, and movie/TV numeric collisions.
- [ ] Add failing pagination tests using multiple pages and pagination headers.
- [ ] Fetch watched movies and shows with `page`, `limit=100`, and compact response data.
- [ ] Stop pagination from authoritative headers; safely treat a headerless first response as complete.
- [ ] Normalize results to composite TMDB identities.
- [ ] Persist only schema version, refreshed timestamp, and deduplicated identities in `trakt-watched.json`.
- [ ] Use a 15-minute in-memory freshness window.
- [ ] Use persisted identities with state `stale` when refresh fails.
- [ ] Return state `unavailable` with an empty set when no successful snapshot exists.
- [ ] Add `ignore_watched=true` to the upstream Trakt recommendations call.
- [ ] Apply the local identity filter as the correctness guard.
- [ ] Extend the Trakt Discover response with watched exclusion freshness.
- [ ] Add Angular contract and warning tests.
- [ ] Show a cached/unavailable warning without replacing valid cards.
- [ ] Verify a known watched movie and show are absent from the live Trakt tab.

### Acceptance criteria

- [ ] Every watched page is consumed.
- [ ] Any watched episode excludes the show.
- [ ] Watched movies and shows are filtered by typed TMDB identity.
- [ ] The cache never stores titles, episode details, timestamps per play, or other raw history.
- [ ] Stale cache remains usable after a Trakt failure.
- [ ] No-cache failure permits results but warns that watched filtering is unavailable.
- [ ] Trakt recommendation failures retain the existing Discover error behavior.

### Verification

From `config/homepage-actions`:

```powershell
python -m unittest -v test_trakt_history
python -m unittest -v test_discover_trakt
```

From `dashboard-app`:

```powershell
rtk npx ng test dashboard --watch=false --include=projects/dashboard/src/app/discover/discover.facade.spec.ts --include=projects/dashboard/src/app/discover/discover-page.spec.ts
```

### Stop conditions

- Do not call Trakt once per card.
- Do not persist raw watch history.
- Do not treat a missing TMDB ID as safe to compare by title.

---

## Issue 4 — Filter Trakt-watched titles from Jellyseerr

**Blocked by:** Issue 3<br>
**Labels:** `Feature`, `backend`, `testing`, `contracts`, `codex-refined`, `ready-for-agent`, `complexity:low`

### What to build

Reuse the watched identity snapshot to remove matching movies and shows from all Jellyseerr Discover feeds.

Do not change Jellyseerr request behavior, availability semantics, or source caching.

### Execution checklist

- [ ] Add failing tests for trending, movie, and TV Jellyseerr feeds containing watched and unwatched identities.
- [ ] Add a collision case where `movie:123` is watched but `tv:123` remains eligible.
- [ ] Apply the watched filter after Jellyseerr response normalization and before serialization.
- [ ] Attach the same watched freshness state used by the Trakt source.
- [ ] Preserve disabled, unavailable, stale-response, poster, and request-state behavior.
- [ ] Run the focused backend suite.
- [ ] Verify a known watched title is absent from each enabled Jellyseerr feed.

### Acceptance criteria

- [ ] All Jellyseerr feed kinds exclude watched identities.
- [ ] Typed identity prevents movie/TV collisions.
- [ ] A stale watched snapshot still filters Jellyseerr.
- [ ] An unavailable snapshot permits results and reports a warning.
- [ ] Jellyseerr disabled and failure responses remain unchanged.
- [ ] Media requests still target the same normalized media identity.

### Verification

```powershell
python -m unittest -v test_discover_exclusions
python -m unittest -v test_automation_preview
```

### Stop conditions

- Do not add a second watched-history fetch inside Jellyseerr handling.
- Do not alter request or acquisition semantics.

---

## Issue 5 — Archive Trakt-watched Hermes picks without losing History

**Blocked by:** Issue 4<br>
**Labels:** `Bug`, `backend`, `frontend`, `contracts`, `testing`, `codex-refined`, `ready-for-agent`, `complexity:medium`

### What to build

Remove Trakt-watched Hermes recommendations from Active immediately while preserving their records in History.

The read path must use projection only. Persistent rotation belongs to the generation commit handled by Issue 6.

### Execution checklist

- [ ] Add failing backend tests for active watched, inactive watched, feedbacked watched, and library-plus-watched Hermes items.
- [ ] Project watched matches with `excluded_reason: "watched_on_trakt"`.
- [ ] Keep the recommendation store unchanged during GET.
- [ ] Add failing Angular tests proving projected watched items leave Active.
- [ ] Include projected items in History even when their stored `active` flag is still true.
- [ ] Make the History Watched filter include `watched_on_trakt`.
- [ ] Show “Watched on Trakt” without changing stored Hermes feedback.
- [ ] Define deterministic label precedence when an item is both in library and watched: show “In library” as the primary badge and retain watched eligibility for the Watched filter.
- [ ] Preserve request state, feedback, timestamps, and card actions.
- [ ] Verify Active and History counts use the projected classification.

### Acceptance criteria

- [ ] A watched Hermes item disappears from Active on the next successful read.
- [ ] The same record remains in History.
- [ ] The Watched filter finds it.
- [ ] Automatic exclusion does not fabricate Hermes feedback.
- [ ] GET does not mutate `recommendations.json`.
- [ ] Existing liked, disliked, skipped, watched, requested, and pagination behavior remains correct.
- [ ] Library-plus-watched precedence is deterministic.

### Verification

```powershell
python -m unittest -v test_discover_exclusions
python -m unittest -v test_generations_api
rtk npx ng test dashboard --watch=false --include=projects/dashboard/src/app/discover/discover-format.spec.ts --include=projects/dashboard/src/app/discover/discover.facade.spec.ts --include=projects/dashboard/src/app/discover/discover-page.spec.ts
```

### Stop conditions

- Do not mark projected rows `active=false` during GET.
- Do not translate Trakt history into fake `liked` or `watched` feedback.

---

## Issue 6 — Prevent Hermes generation from restoring excluded titles

**Blocked by:** Issues 1 and 5<br>
**Labels:** `Bug`, `backend`, `contracts`, `testing`, `codex-refined`, `ready-for-agent`, `complexity:medium`

### What to build

Make library and watched exclusions authoritative during Hermes generation so future runs cannot retain or recreate ineligible titles.

### Execution checklist

- [ ] Add failing tests for generation context containing `watched_media_ids`.
- [ ] Define and test the authenticated internal generation snapshot contract separately from the public dashboard Hermes GET; keep revision, presented identities, context, and typed deny sets out of browser responses.
- [ ] Add failing tests proving excluded Active identities are absent from `required_retain`.
- [ ] Add failing tests for new watched candidate rejection as `already_watched`.
- [ ] Add failing tests proving an existing watched or in-library Active row rotates during a successful generation commit.
- [ ] Preserve typed identities through context, candidate validation, and rejection responses.
- [ ] Extend the generation exclusion snapshot with library, tracked, and watched sets.
- [ ] Remove excluded identities from automatic keeper logic.
- [ ] Add `watched_media_ids` to the server-built Hermes context.
- [ ] Reject new watched candidates before acceptance.
- [ ] Allow the transaction to rotate existing excluded items while preserving feedback and request fields.
- [ ] Update the Hermes generation prompt to treat watched IDs as a deny list and to avoid resubmitting them as keepers.
- [ ] Keep stale exclusion failures soft: log sanitized degradation and use the available cached sets.
- [ ] Add proxy contract tests proving browser `/api/internal/*`, `/api/discover/hermes/generations`, and `/api/discover/hermes/sync` return 404; preserve browser access to the public Hermes read and Request More queue signal.
- [ ] Keep Hermes generation and collection sync on the direct host cron routes at `http://localhost:8085`; the dashboard must not proxy them.
- [ ] Run the full generation and recommendation-store suites.

### Acceptance criteria

- [ ] Hermes receives watched, library, and tracked typed identity sets.
- [ ] Excluded items are never required keepers.
- [ ] New watched candidates return `already_watched`.
- [ ] Existing excluded Active rows rotate to History on commit.
- [ ] Never-twice and presented-identity invariants remain intact.
- [ ] Feedback, request state, and timestamps survive rotation.
- [ ] The prompt and server enforcement describe the same rules.
- [ ] The public dashboard contract exposes only browser-safe fields and exclusion freshness; Hermes reads generation-only revision/context from the separately authenticated internal snapshot.
- [ ] Browser private Hermes attempts return 404, while `/api/discover/hermes` and `/api/discover/hermes/request-more` remain browser-accessible and generation/sync use the direct host cron routes.

### Verification

```powershell
python -m unittest -v test_generations_api
python -m unittest -v test_recommendations_store
python -m unittest -v test_poster_enrichment
```

### Stop conditions

- Do not depend on the Hermes prompt as the only enforcement layer.
- Do not weaken `presented_media_ids` or composite identity rules.
- Do not rotate unrelated untouched Active rows.

---

## Issue 7 — Complete local Trakt reconnect and Discover acceptance

**Blocked by:** Issue 6<br>
**Labels:** `testing`, `docs`, `backend`, `frontend`, `codex-refined`, `ready-for-agent`, `complexity:medium`

### What to build

Run the complete local verification matrix, confirm the real user-visible behavior, and align setup documentation with the implemented authentication and exclusion contracts.

This issue is a verification gate, not permission for unrelated cleanup.

### Execution checklist

- [ ] Confirm all issues share the approved contracts and no temporary compatibility path remains.
- [ ] After renewable OAuth is verified, remove `TRAKT_ACCESS_TOKEN` from configuration, Compose, and setup documentation; confirm the final gate has no temporary compatibility path.
- [ ] Run the full backend test suite.
- [ ] Run the complete Angular quality gate.
- [ ] Validate Compose rendering.
- [ ] Validate PowerShell syntax.
- [ ] Run `git diff --check`.
- [ ] Recreate `homepage-actions` with the writable state mount and active `requests` profile.
- [ ] Keep or restore the documented Docker hot-reload dashboard.
- [ ] Confirm Trakt movies and shows return `200`.
- [ ] Confirm token and watched files exist only in the ignored state directory.
- [ ] Confirm logs and browser responses contain no credentials or raw history.
- [ ] Verify “The Bear” is absent from Hermes Active and present in History as “In library.”
- [ ] Verify one known watched movie and one known watched show are absent from Hermes Active, Jellyseerr, and Trakt.
- [ ] Verify a watched Hermes record remains in History and matches the Watched filter.
- [ ] Verify no warning appears after a fresh sync.
- [ ] Use controlled tests—not live token corruption—to prove stale and unavailable warnings.
- [ ] Update setup and architecture documentation with reconnect and cache behavior.
- [ ] Review final scoped diffs against the initial dirty baseline.
- [ ] Leave the work unstaged and uncommitted unless the user separately requests publication.

### Acceptance criteria

- [ ] `python -m unittest discover -v` passes.
- [ ] `npm run quality` passes.
- [ ] `docker compose config` passes.
- [ ] The live Trakt API returns authenticated recommendations.
- [ ] All three Active sources exclude owned and watched titles.
- [ ] Hermes History preserves automatically excluded records.
- [ ] Fresh, stale, and unavailable UX is verified.
- [ ] Renewable OAuth is verified and `TRAKT_ACCESS_TOKEN` is removed, so no temporary compatibility path remains.
- [ ] Credentials and private history remain local and ignored.
- [ ] Documentation matches the shipped behavior.
- [ ] Browser responses and reconnect/degradation errors contain no credentials, raw watch history, or generation-only identity sets.
- [ ] Browser `/api/internal/*`, `/api/discover/hermes/generations`, and `/api/discover/hermes/sync` return 404; browser `/api/discover/hermes` and `/api/discover/hermes/request-more` remain available; generation and collection sync remain owned by the direct-host cron routes `POST http://localhost:8085/discover/hermes/generations` and `POST http://localhost:8085/discover/hermes/sync`.
- [ ] Unrelated dirty work remains intact.

### Verification

From `config/homepage-actions`:

```powershell
python -m unittest discover -v
```

From `dashboard-app`:

```powershell
rtk npm run quality
```

From the repository root:

```powershell
docker compose config
pwsh -NoProfile -Command "[void][scriptblock]::Create((Get-Content -Raw .\install.ps1))"
rtk git diff --check
docker compose --profile requests up -d --force-recreate homepage-actions
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate dashboard
```

Then complete browser acceptance at:

```text
http://127.0.0.1:3000/discover
```

### Stop conditions

- If a full gate has an unrelated pre-existing failure, record exact evidence and stop instead of broadening scope.
- Do not repair failures by deleting coverage, relaxing types, or weakening exclusion rules.
- Do not damage or deliberately expire the real Trakt token to test failure handling.

---

## Linear publication procedure

Once publication is authorized:

1. Create the parent issue with the approved metadata.
2. Create Issue 1 and Issue 2 under the parent with no blockers.
3. Create Issue 3 under the parent, blocked by Issue 2.
4. Create Issue 4 under the parent, blocked by Issue 3.
5. Create Issue 5 under the parent, blocked by Issue 4.
6. Create Issue 6 under the parent, blocked by Issue 1 and Issue 5.
7. Create Issue 7 under the parent, blocked by Issue 6.
8. Fetch every created issue and verify:
   - Parent relationship.
   - Blocker identifiers.
   - `Ready` state and High priority.
   - Exact labels.
   - No assignee, estimate, cycle, or due date.
   - Complete Markdown body without truncated acceptance criteria.
