# Task 8 verification report

## TDD evidence

- Red: `installer.tests.test_gpu` initially failed because the new GPU module was absent.
- Green: focused GPU/Compose/setup/CLI tests pass (56 tests, one platform skip).

## Verification

- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s installer/tests -q` — 247 tests pass, one platform-dependent skip.
- Compose `core`, NVIDIA, VA-API, dev+NVIDIA, and dev+VA-API `config --quiet` matrices — pass. VA-API checks supplied numeric `RENDER_GID`/`VIDEO_GID` through the environment for the matrix.
- `bash -n install.sh` — pass.
- `git diff --check` — pass.

## Implementation

- Added read-only, injectable NVIDIA and VA-API probes with bounded command timeouts and typed capability failures.
- Added explicit `auto|none|nvidia|vaapi` CLI/Compose modes; auto detection raises an approval checkpoint unless explicitly confirmed and never selects an overlay during doctor-only inspection.
- Added VA-API device/group/architecture/ffmpeg validation and numeric group wiring in `docker-compose.vaapi.yml`.
- Kept Jellyfin encoding preferences untouched; only device/runtime exposure is owned here.
- Added GPU detail to lifecycle and doctor diagnostics while preserving redacted reports and dry-run boundaries.

Commit: `f3d8a6d` (`feat(installer): support Linux GPU passthrough`)

## Review-fix verification

- Added regression coverage proving explicit unavailable GPU modes make doctor return `needs-attention` with a nonzero stable severity.
- `up` now resolves saved/requested NVIDIA or VA-API capabilities before stale-container cleanup or Compose startup; dry-run remains read-only.
- Runtime ffmpeg/NVIDIA probes use bounded `--pull=missing`, allowing a missing probe image to be fetched safely without touching media or installer state.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s installer/tests -q` — 250 tests pass, one platform-dependent skip.
- Focused GPU tests — 12 pass.
- Core, NVIDIA, VA-API, dev+NVIDIA, and dev+VA-API Compose `config --quiet` matrices — pass.
- `bash -n install.sh` and `git diff --check` — pass.

## Final dry-run safety fix

- `run_up(dry_run=True)` now skips GPU probes entirely and reports requested hardware as `unverified`; planned overlay arguments remain visible, but no `nvidia-smi`, `docker run`, or image pull can occur.
- Normal lifecycle activation still validates the selected GPU mode first and probes missing runtime images with bounded `--pull=missing`.
- Regression test confirms dry-run has no GPU probe/pull side effects.
- Final installer suite: 251 tests pass, one platform-dependent skip.

Fix commit: `a97c4d2` (`fix(installer): keep GPU dry-runs read-only`)

## Final VA-API lifecycle fix

- `run_up` now resolves explicit or saved VA-API capability before Compose activation, atomically commits the discovered numeric `RENDER_GID`/`VIDEO_GID` values to the Compose environment, and then starts the selected overlay.
- Explicit lifecycle GPU/profile choices are persisted to installer state on mutating runs. Dry-runs may report injected planned values but never write `.env` or state and never run real probes.
- Regression coverage verifies VA-API group wiring, state persistence, Compose activation ordering, and dry-run immutability.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest installer.tests.test_gpu -q` — 15 tests pass.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s installer/tests -q` — 253 tests pass, one platform-dependent skip.
- Core, NVIDIA, VA-API, dev+NVIDIA, and dev+VA-API Compose `config --quiet` matrices — pass.
- `bash -n install.sh` and `git diff --check` — pass.

Fix commit: `80cffc7` (`fix(installer): persist VA-API runtime groups`)

## Healthy diagnostics and installer-wide dry-run fix

- Doctor now treats healthy `available` GPU diagnostics (and intentionally `disabled` diagnostics) as non-error statuses while retaining nonzero severity for unavailable, unsupported, and confirmation-required modes.
- Foundation and lifecycle dry-runs skip real GPU probes/pulls; injected detector details remain explicitly `unverified` with planned overlays and VA-API values visible without writing state or `.env`.
- Regression coverage verifies complete healthy explicit NVIDIA diagnostics and probe-free NVIDIA/VA-API foundation dry-runs.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest installer.tests.test_gpu -q` — 17 tests pass.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s installer/tests -q` — 255 tests pass, one platform-dependent skip.
- Core, NVIDIA, VA-API, dev+NVIDIA, and dev+VA-API Compose `config --quiet` matrices — pass.
- `bash -n install.sh` and `git diff --check` — pass.

Fix commit: `69a153a` (`fix(installer): classify healthy GPU diagnostics`)

## Final GPU dry-run and auto-state fix

- Injected detector failures and unconfirmed auto candidates are now handled as read-only `unverified` dry-run reports instead of raising; normal mutating runs still fail unavailable explicit modes and require confirmation for auto.
- Confirmed auto foundation activation now durably saves the resolved concrete GPU mode before later journal stages, so subsequent saved lifecycle runs do not require another auto confirmation.
- Regression coverage verifies probe-free unavailable/unconfirmed dry-runs across foundation and `up`, plus confirmed-auto state persistence and saved-mode activation.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest installer.tests.test_gpu -q` — 19 tests pass.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s installer/tests -q` — 257 tests pass, one platform-dependent skip.
- Core, NVIDIA, VA-API, dev+NVIDIA, and dev+VA-API Compose `config --quiet` matrices — pass.
- `bash -n install.sh` and `git diff --check` — pass.

Fix commit: `d27e4e3` (`fix(installer): finalize GPU dry-run and auto state`)

## Complete GPU lifecycle persistence fix

- VA-API foundation dry-runs now validate Compose with a disposable 0600 planning environment containing discovered numeric groups or inert placeholders; the real `.env`, installer state, media, and downloads remain untouched, and temporary planning secrets are redacted.
- Mutating `up` now saves a resolved concrete GPU mode even when it was inherited from saved `auto`, so a confirmed selection is reused without reconfirmation.
- Regression coverage verifies temporary VA-API planning and saved-auto convergence.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest installer.tests.test_gpu -q` — 21 tests pass.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s installer/tests -q` — 259 tests pass, one platform-dependent skip.
- Core, NVIDIA, VA-API, dev+NVIDIA, and dev+VA-API Compose `config --quiet` matrices — pass.
- `bash -n install.sh` and `git diff --check` — pass.

Fix commit: `aed3325` (`fix(installer): complete GPU lifecycle persistence`)

## Follow-up lifecycle persistence fix

- Foundation and `up` dry-runs no longer call activation-time `gpu_environment`
  validation for injected VA-API results. Complete numeric IDs are retained in
  the disposable plan/report; missing or malformed IDs remain unverified and
  Compose receives inert numeric placeholders without mutating `.env`, state,
  media, or downloads.
- A mutating `up` inheriting saved `gpu_mode: auto` persists the confirmed
  concrete NVIDIA or VA-API mode. VA-API `RENDER_GID` and `VIDEO_GID` values are
  committed to `.env` before Compose startup; strict capability and
  confirmation checks remain unchanged for activation.
- Added focused regressions for missing dry-run VA-API IDs and saved-auto
  VA-API convergence.

## Final dry-run planning-environment fix

### Root cause

The existing `_compose_planning_environment` helper only created a temporary
environment for VA-API previews. A fresh dry-run for `none` or `nvidia` left
the real `.env` absent and passed that nonexistent path to `docker compose
config`. The VA-API branch also used `RENDER_GID=0` and `VIDEO_GID=0` when an
injected preview result omitted host IDs, producing duplicate root-group
placeholders. Finally, redacting secrets while copying the plan changed the
values Compose would validate. The safe boundary is to copy the complete
planned document into a mode-0600 disposable file whenever the real `.env` is
absent (and for VA-API previews), retain actual planned values only in that
unlinked file, and rely on existing command/report redaction for output.

### TDD evidence

- Red (before production edits):
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=installer python3 -m unittest installer.tests.test_gpu.GpuProbeTests.test_foundation_dry_run_fresh_env_uses_disposable_plan_for_every_gpu_mode -v`
  failed for fresh `none`/`nvidia` because Compose received the missing real
  `.env`, and failed for VA-API because the disposable copy contained
  redacted secrets and duplicate `0` group placeholders.
- Green (after the minimal fix):
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=installer python3 -m unittest installer.tests.test_gpu.GpuProbeTests.test_foundation_dry_run_fresh_env_uses_disposable_plan_for_every_gpu_mode installer.tests.test_gpu.GpuProbeTests.test_foundation_vaapi_dry_run_without_detector_groups_uses_placeholders -v`
  — 2 tests passed. The regression verifies all GPU modes use a disposable
  0600 file for a fresh plan, planned non-secret values and credentials are
  preserved for Compose, redaction values are supplied to the command seam,
  distinct `65534`/`65533` placeholders are used, the file is removed, and
  the real `.env`, installer state, media, and downloads remain absent.
- A follow-up focused red-green check caught that the broadened temporary-file
  branch would have added VA-API-only keys to fresh non-VA-API plans. The
  focused test failed for `none` and `nvidia`, then passed after guarding the
  placeholders to VA-API mode; the same 2-test focused command remained green.

### Verification

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=installer python3 -m unittest discover -s installer/tests -q` — 262 tests passed, one platform-dependent skip.
- `bash -n install.sh` — pass.
- `git diff --check` — pass.
- Compose `config --quiet` matrices for core, NVIDIA, VA-API, dev+NVIDIA,
  and dev+VA-API — all pass; VA-API used numeric `RENDER_GID=107` and
  `VIDEO_GID=44`.
- Direct `install.sh setup --dry-run` attempts for fresh `none`, `nvidia`,
  and `vaapi` reached host/storage planning but this machine's Docker Engine
  was offline, so Docker preflight returned its stable unavailable-daemon
  error before Compose. No `.env`, installer state, media, downloads, image,
  or container mutation occurred.
