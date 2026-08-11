# Renewable Trakt OAuth Design

## Decision

Replace the fixed Trakt access token with locally persisted OAuth token state that the Live API can refresh automatically.

One device authorization is required to create the first refresh token. After that authorization, normal access-token expiry must not require user action.

This design implements the authentication scope of Issue 2 in `trakt-aware-discover-linear-execution-plan.md`. Watched-title filtering and the other exclusion issues remain out of scope.

## Goals

- Refresh the Trakt access token before it expires.
- Refresh and retry once when an authenticated Trakt request returns `401`.
- Prevent concurrent requests from rotating the same refresh token more than once.
- Persist every replacement access token and refresh token atomically.
- Detect unrecoverable authorization failures and return an actionable reconnect state.
- Keep all Trakt credentials out of Git, logs, browser responses, and Angular.
- Provide a one-time PowerShell device-authorization workflow.

## Non-goals

- Silent recreation of user consent after both tokens become invalid. Trakt requires user authorization in that case.
- Dashboard-based credential entry or account settings.
- Watched-history synchronization or recommendation filtering.
- Changes to Hermes or Jellyseerr behavior.

## Components

### Token state

The host stores an ignored JSON file in a local state directory. Only `homepage-actions` receives the directory through a writable `/state` mount. The application source mount remains read-only.

The file contains:

- schema version;
- access token;
- refresh token;
- access-token expiry time;
- creation time required by Trakt refresh requests.

Writes use a temporary file in the same directory followed by `os.replace`. A failed or interrupted write must leave the last complete token state intact.

### Trakt OAuth client

A focused backend client owns authenticated Trakt requests. It receives injectable HTTP transport, clock, and token-state path dependencies so tests do not use live credentials or wall-clock timing.

For each authenticated request, the client:

1. Loads and validates the current token state.
2. Refreshes it when fewer than 60 seconds remain before expiry.
3. Sends the original request with the current access token.
4. On `401`, refreshes once and retries the original request once.
5. Returns the upstream result or a sanitized connection error.

A process-wide lock covers state reload, refresh, and atomic replacement. A waiting request reloads the state after acquiring the lock and reuses a token already refreshed by another request.

The client never loops after the single retry.

### Device authorization

`install.ps1 -Mode connect-trakt` starts Trakt device authorization with the configured client ID. It prints only the verification URL, user code, and safe progress messages.

The workflow handles authorization pending, slowdown, denial, expiry, and success. Success atomically stores the full token response. Failure does not overwrite an existing valid state file. Tokens and the client secret are never printed.

### Configuration

Compose provides:

- `TRAKT_CLIENT_ID`;
- `TRAKT_CLIENT_SECRET`;
- `TRAKT_TOKEN_PATH`, pointing inside `/state`.

`TRAKT_ACCESS_TOKEN` remains a migration fallback only until renewable OAuth is verified. It is then removed from Compose, `.env.example`, and setup documentation.

## Error handling

| Condition | Behavior |
| --- | --- |
| Access token near expiry | Refresh before sending the request. |
| First authenticated request returns `401` | Refresh, persist both replacement tokens, and retry once. |
| Another request already refreshed the token | Reload and reuse the new state without a second refresh. |
| Refresh is temporarily unavailable | Return a sanitized temporary Trakt error; preserve existing state. |
| Refresh token is rejected or state is invalid | Return a sanitized `reconnect_required` connection state. |
| Device authorization fails or expires | Preserve prior state and print a safe retry instruction. |

The backend must not send raw urllib errors to Angular. The Trakt tab converts `reconnect_required` into an explicit “Trakt reconnect required” state with the local command to run. Other temporary upstream failures retain a retryable temporary-error state.

## Security

- Token state is ignored by Git and stored outside the application source tree.
- Only `homepage-actions` receives the state mount.
- The dashboard proxy never receives OAuth credentials.
- Logs and API responses contain error categories, not token values or upstream response bodies that could contain credentials.
- Tests use synthetic credentials.
- Device authorization never asks the user to paste a secret or token into chat.

## Verification

Automated tests must first fail and then pass for:

- token-state loading and validation;
- atomic replacement and preservation after a failed write;
- proactive refresh near expiry;
- one refresh and one retry after `401`;
- no retry loop after a second `401`;
- concurrent requests performing at most one refresh;
- refresh rejection producing `reconnect_required` without secrets;
- device authorization pending, slowdown, denial, expiry, success, and non-destructive failure;
- frontend mapping of reconnect-required and temporary Trakt errors.

Final verification includes the full backend suite, Angular quality gate, Compose rendering, PowerShell syntax, both live Trakt recommendation types, credential-leak checks, and live browser acceptance on port 3000.

## Rollout

1. Add the tested token store and renewable OAuth client.
2. Add the state mount and migration configuration.
3. Add and test `connect-trakt`.
4. Complete one device authorization with the user.
5. Recreate `homepage-actions` and verify movies and shows return `200`.
6. Remove the fixed access-token fallback.
7. Re-run the complete verification matrix and restore the dashboard on port 3000.
