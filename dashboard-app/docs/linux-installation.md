# Linux installation

The Linux installer is a thin Bash launcher around the Python standard-library
installer. Run it from any directory; it resolves the repository containing the
script before invoking Python.

```bash
./install.sh --help
./install.sh setup
```

Python 3.10 or newer, Docker Engine, and Docker Compose v2.24.4 or newer are
required. Host Node.js is not required for stack setup. The supported host
families are Arch/Omarchy, Ubuntu/Debian, and Fedora. Other distributions are
supported when an already-working Docker Engine and Compose installation pass
`doctor`.

## First run

The interactive setup asks for the media and download locations, a secure
qBittorrent password, Jellyfin administrator credentials, and any unresolved
network exposure decision. Optional profiles and GPU mode remain explicit CLI
choices. It shows a summary before changing the host.

```bash
./install.sh setup
```

The public Linux commands are:

| Command | Purpose |
| --- | --- |
| `setup` | Prepare the host, create the environment, start the foundation, and reconcile the core services. |
| `doctor` | Report Docker, host, storage, network, state, and image prerequisites without pulling. |
| `up` / `down` | Start or stop the selected Compose stack. |
| `configure` | Reconcile managed service settings after a guided checkpoint. |
| `frontend-dev` | Install frontend dependencies for Demo development. |
| `redeploy-dashboard` | Rebuild and recreate only the production dashboard. |
| `connect-trakt` | Run Trakt device authorization and save renewable state atomically. |
| `update` | Back up approved configuration and update immutable image metadata. |
| `update --rollback RUN_ID` | Restore one recorded update with its generated Compose override. |

Every mutating command supports `--dry-run` where applicable. A dry-run only
plans commands and renders a redacted report: it does not write `.env`, state,
service configuration, media, downloads, images, containers, or firewall
rules.

## Headless setup

For automation, supply non-secret values through `LUMEN_*` variables or a
version-1 answers file. Supply passwords only through a protected environment
secret; never put them in command arguments, an answers JSON file, shell
history, CI logs, or a checked-in file.

```bash
export LUMEN_ROOT_PATH=/srv/lumen-media
export LUMEN_DOWNLOADS_PATH=/srv/lumen-downloads
export LUMEN_QBT_PASSWORD="use-a-secret-store"

./install.sh setup \
  --non-interactive \
  --network-mode local \
  --gpu-mode none
```

The installer resolves CLI options before `LUMEN_*`, then non-secret answers,
then interactive defaults. A headless run fails at an unapproved migration or
credential checkpoint instead of guessing. Use `--confirm` only when the
automation has reviewed the exact intended ownership/configuration change.

An answers file contains non-secret values only:

```json
{
  "schema_version": 1,
  "answers": {
    "ROOT_PATH": "/srv/lumen-media",
    "DOWNLOADS_PATH": "/srv/lumen-downloads",
    "TZ": "America/Sao_Paulo",
    "NETWORK_MODE": "local",
    "QBT_PASSWORD": {"env": "LUMEN_QBT_PASSWORD"}
  }
}
```

## Ownership, timezone, and storage

`PUID`, `PGID`, and `TZ` are detected from the invoking user and host. A
non-root invocation uses the current UID/GID. A command run through `sudo`
uses `SUDO_UID`/`SUDO_GID`; a genuine root invocation must provide explicit,
nonzero ownership IDs. Existing values are preserved and drift is reported.

The media root and downloads path must be separate, explicit absolute paths.
Do not use the repository, `/`, or a path containing existing symlinks as a
media target. The installer validates ownership, writability, free space, and
container visibility, and creates only approved subdirectories. It never
deletes or cleans media or downloads.

The installer writes `.env` with an atomic replace and mode `0600`. Installer
state, journals, manifests, and backups live under the ignored
`.state/installer/` tree with directories `0700` and files `0600`.

## Local-only and LAN access

Fresh installs are local-only by default: Jellyfin and management UIs bind to
`127.0.0.1`, and `homepage-actions:8085` is always loopback-only. qBittorrent's
peer TCP and UDP ports remain externally reachable for torrent connectivity.

To intentionally expose Jellyfin on a LAN, select LAN mode and provide a
validated host name or address:

```bash
./install.sh setup --network-mode lan --public-host media.example.lan
```

The LAN decision binds Jellyfin to `0.0.0.0` and aligns its remote-access
policy. Management UIs remain loopback-only unless their Compose/network
contract is changed deliberately. Configure a firewall and, when appropriate,
TLS/reverse proxy separately; the installer does not silently open ports,
install a firewall, or change router rules.

When adopting an older `.env` without `JELLYFIN_BIND_ADDRESS`, the installer
reports possible legacy LAN exposure. Interactive setup asks whether to
preserve `0.0.0.0` or migrate to local-only access. Non-interactive setup stops
with a drift error before changing Compose or `.env`.

Docker Engine access is a host privilege boundary. The installer never
silently enables rootless Docker, edits group membership, replaces conflicting
packages, or runs privileged package commands. Use the distribution's approved
Docker installation and graphical authorization for any genuinely required
administrator action. Review Docker socket access and firewall policy before
exposing a service beyond localhost.

## qBittorrent adoption

`QBT_PASSWORD` is authoritative; `STACK_PASSWORD` is retained only as a
compatibility alias. On a fresh config the installer uses the bounded startup
log checkpoint when available. On an adopted config it authenticates with the
existing `.env` credential first. A mismatch requests the separately supplied
`LUMEN_QBT_CURRENT_PASSWORD` or stops at a guided recovery checkpoint.

The installer never resets qBittorrent by editing its config files. It verifies
the selected password by authenticating again before updating `.env`, then
reconciles the approved save path and the `sonarr`/`radarr` categories while
preserving unrelated categories. Keep the configured peer port reachable on
both TCP and UDP; do not replace it with a loopback-only binding.

## Seerr and optional profiles

The request service remains named `jellyseerr` and keeps the `JELLYSEERR_*`
environment/backend contract. The installer backs up `config/jellyseerr`
before adoption. A fresh config is created with the image's expected numeric
ownership; changing ownership recursively on an existing config requires an
explicit confirmation. The installer never removes that config or media data.

Optional profiles are checkpoints, not implicit activation:

```bash
./install.sh setup --profile requests --profile subtitles
./install.sh up --profile requests --profile subtitles
```

Enable `JELLYSEERR_ENABLED=true` or `BAZARR_ENABLED=true` only after the
corresponding service is configured and its capability/health check succeeds.
Maintenance (`maintenance`), indexer tools (`indexer-tools`), and AI (`ai`)
remain disabled until their own guided credentials and health checks pass.
Unsupported providers, languages, or destructive maintenance policies are
handed off for manual review rather than guessed.

## GPU modes

The supported modes are `none`, `auto`, `nvidia`, and `vaapi`:

```bash
./install.sh setup --gpu-mode nvidia
./install.sh setup --gpu-mode vaapi
```

NVIDIA requires both `nvidia-smi` and a container runtime probe. VA-API
requires `/dev/dri`, numeric render/video group IDs, architecture validation,
and a Jellyfin ffmpeg capability check. `auto` detects capabilities but does
not activate an overlay without confirmation. The installer does not alter
Jellyfin encoding settings until the Jellyfin adapter owns that reconciliation.

## Update, rollback, and recovery

Review an update before confirming it:

```bash
./install.sh update --dry-run
./install.sh update --confirm
```

The manifest records approved `.env`, runtime state/config paths, Compose
files, active profiles, GPU selection, image references, repository digests,
and local build image IDs. Registry rollback entries use the recorded
`repository@sha256:digest`; local build services use immutable
`lumen-rollback/<service>:<run-id>` tags with `pull_policy: never`.

If a pull, build, recreate, or health step fails, the run ID remains available:

```bash
./install.sh update --rollback RUN_ID --confirm
```

Rollback stops affected services, moves post-update approved configuration to a
recoverable failed-run directory, restores the backup atomically, and starts
with the generated override. Media and downloads are never part of the
manifest or rollback operation. Keep the run ID and inspect the redacted
report; do not copy secrets into issue reports.

## Acceptance on supported hosts

Before a real host change, run the read-only gates:

```bash
./install.sh doctor --dry-run
./install.sh setup --dry-run --gpu-mode none
```

Then validate the selected host family with Docker Compose config rendering,
the service health checks, loopback/API access, and a qBittorrent peer-port
connectivity check. Repeat the clean local default and an intentional LAN
scenario on each supported family:

- Arch or Omarchy: use the distro Docker packages, verify Docker Engine and
  Compose versions, and confirm the host firewall leaves the peer TCP/UDP port
  reachable.
- Ubuntu/Debian: verify the official stable Docker apt repository or an
  already-passing installation; verify the same network and storage checks.
- Fedora: verify the official stable Docker dnf repository or an
  already-passing installation; verify SELinux/firewall policy with the host
  administrator.

For each host, check the dashboard on `127.0.0.1:3000`, the authenticated API
health endpoint on `127.0.0.1:8085`, Jellyfin reachability according to the
selected bind mode, optional profile health only after its checkpoint, and a
second idempotent `up`/`configure` run. Keep Docker and filesystem logs free of
credentials when recording acceptance results.
