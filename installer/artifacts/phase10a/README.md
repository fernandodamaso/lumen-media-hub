# Phase 10A internal-storage guard

This is the only Phase 10A guard artifact. It is separate from the historical
`installer/artifacts/phase9/` ARQUIVOS artifacts, which must not be installed.

The supervisor accepts only:

- `/home/admin/lumen-downloads` as `/downloads`;
- `/home/admin/media/media` as `/data/media`; and
- filesystem UUID `33e8776315094a8da779ef612107500b`.

It renders `docker-compose.yml` plus `docker-compose.separate.yml`, enables
only the intentional `subtitles` profile when `BAZARR_ENABLED=true`, requires
`restart: "no"` for writer containers, measures both actual filesystems every
five seconds, and writes a redacted operational state file outside media and
download trees. qBittorrent API or identity failure stops the downloader and
suspends writers; only hashes previously paused by this guard may be resumed.

The unit is staged until the live Compose render, qBittorrent inventory, and
observe/forced-failure/recovery checks pass. Enabling `DISK_GUARD_ENABLED` in
`.env` alone never proves that this process is running.
