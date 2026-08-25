# Sonarr queue hygiene operations

Queue hygiene starts in `observe` mode and only targets completed Sonarr queue rows whose warning begins with `Not an upgrade for existing episode file(s).` Routine active downloads and candidates still inside the grace period are not treated as review findings.

## Circuit breaker

Automatic cleanup opens a persisted circuit breaker when a cleanup mutation cannot be verified, including when expected qBittorrent hashes disappear, Sonarr queue IDs remain, or a post-mutation verification request fails. While the circuit is open, automatic cleanup is disabled.

Before resetting the circuit:

1. Open **Reports → Sonarr queue hygiene** and review the persisted error and verification state.
2. Confirm the affected torrents still exist in qBittorrent and that Sonarr is reachable.
3. Fix the underlying connectivity or queue-state problem.
4. Reset the circuit through the dashboard proxy:

```bash
curl -X POST http://localhost:3000/api/automation/queue-hygiene/reset \
  -H 'Content-Type: application/json' \
  --data '{"confirm":"reset-circuit"}'
```

If `DASHBOARD_PORT` is not `3000`, replace the port in the URL. The dashboard proxy injects the actions token; do not place `ACTIONS_TOKEN` in shell history or client-side scripts.

A successful reset returns JSON with `"circuitOpen": false`. Run **Preview now** in Reports after the reset before re-enabling or relying on automatic cleanup.
