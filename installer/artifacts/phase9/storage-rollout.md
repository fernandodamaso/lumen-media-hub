# Separate-storage rollout artifact

This directory is a staged Phase 2 handoff for the fixed Linux host. It is
not an installation script. Do not copy units into `/etc/systemd/system`, run
`systemctl`, restart Compose, or move media as part of Phase 2.

The intended persisted values are:

```text
STORAGE_MODE=separate
ROOT_PATH=/run/media/admin/ARQUIVOS
DOWNLOADS_PATH=/home/admin/lumen-downloads
LIBRARY_MOUNT_UUID=B8A426BFA4267FCC
```

The mount unit binds the permanent library filesystem by UUID. The writer
unit requires and binds to that mount and `docker.service`, verifies complete
mount identity metadata and explicit writable options, and starts only the
enabled owned writers through the separate Compose overlay. Saved profiles are
read from installer state; `subtitles` starts Bazarr only when
`BAZARR_ENABLED=true`, and `maintenance` starts Unpackerr. Disabled optional
services are never included in the start argv. The stop path owns all writer
names, including optional stale containers, without enabling them. The helper
preserves `COMPOSE_FILE` and the existing host override, and the overlay sets
`restart: "no"` for every owned writer so Docker does not compete with
systemd. The base Compose contract remains available for the default shared
mode.

## Later rollout sequence

1. Freeze downloader and *arr writers, then back up `.env` and the relevant
   service configuration/state. Keep the backup outside the media trees.
2. Confirm `findmnt --json --target /run/media/admin/ARQUIVOS
   --output TARGET,UUID,OPTIONS,FSTYPE` reports the exact target, UUID
   `B8A426BFA4267FCC`, a non-empty filesystem type, and explicit `rw` (not
   only an assumed default). Confirm the staging path is writable on the main
   disk.
3. Review the two unit files for the host’s actual NTFS driver and UID/GID.
   Check effective access as the configured service identity, not merely as
   root: `PUID:PGID` must be able to write `/run/media/admin/ARQUIVOS/media`
   for Arr/Bazarr/Unpackerr and `/home/admin/lumen-downloads` for qBittorrent.
   Jellyfin/backend access to the media child must be readable. Install and
   enable the mount unit first; enable the writer unit only after the mount is
   active.
4. Render the stack with `STORAGE_MODE=separate` and verify qBittorrent sees
   only `/downloads`; Sonarr/Radarr/Unpackerr see writable `/data/media` plus
   `/downloads`; Bazarr sees only writable `/data/media`; and Jellyfin/backend
   see read-only `/data/media`. Do not change the stable
   `/data/media/movies` or `/data/media/tv` roots.
5. Copy-and-verify any cross-filesystem imports. Do not assume hardlinks work
   between `/home/admin/lumen-downloads` and `/run/media/admin/ARQUIVOS`.
6. Observe health, import paths, mount-loss stop behavior, and logs before accepting the rollout. Keep
   the backup and prior service state until rollback is explicitly accepted.

Future dependency: the Phase 5 recovery path must allow safe imports and
verified cleanup below the 75 GiB startup floor while the downloader remains
paused. Phase 4 verification must add read-only staging access for the backend
before it relies on staging contents.

Phase 2 only stages these contracts. It does not migrate existing downloads,
rewrite persisted qBittorrent paths, install units, or change the live host.
