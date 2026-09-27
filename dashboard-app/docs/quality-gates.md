# Quality gates

`npm run quality` is the default commit gate. It runs the full static-check suite in parallel and fails if any check fails.

## Validation runtime

Validate with **Node 22.22.3**, the exact version CI uses. `dashboard-app/.node-version` pins it for version managers such as mise, nvm, and fnm; it never changes the machine-wide default Node. If your shell still resolves a different Node, run commands through the pinned runtime (for example `mise x node@22.22.3 -- npm run quality`).

## Scripts

| Script | When | What |
|---|---|---|
| `lint:fast` / `lint:agent` / `lint:styles:agent` | Day-to-day / idle agent | Fast feedback only |
| `lint` / `lint:styles` | Targeted strict checks | Rigorous ESLint (zero-warning) and Stylelint |
| `lint:fix` / `lint:styles:fix` | Safe autofix | Fix lint and style issues when appropriate |
| `typecheck` | Before commit / CI | TypeScript contract check |
| `quality:duplicates` | Before commit / CI | jscpd duplication scan |
| `quality:dead-code` | Before commit / CI | Knip unused code / exports / deps |
| `quality:architecture` | Before commit / CI | Dependency Cruiser architecture rules |
| `quality` | Commit gate / CI | `lint` + `typecheck` + `lint:styles` + `quality:duplicates` + `quality:dead-code` + `quality:architecture` |

## Result Semantics

- `0` means the process passed.
- Non-zero means a blocking failure.
- ESLint warnings are blocking: `lint` runs with `--max-warnings=0`, so any warning fails the gate (zero-warning policy), including SonarJS findings.
- Knip configuration hints stay visible and should be investigated, not hidden.
- jscpd below the configured threshold stays informational.
- Dependency Cruiser warnings are informational unless a rule is configured as `error`.

## Git Hooks

Checked in under `githooks/`. Install with:

```bash
npm run hooks:install
```

`prepare` runs the same on `npm install` and sets `core.hooksPath=githooks` for this repo only.

- `pre-commit` → `npm run quality`
- `pre-push` is intentionally absent to avoid repeating the same gate twice.

`--no-verify` is prohibited for both commits and pushes. Fix the failing check and rerun the gate; never bypass the project's quality hooks.

## Correction Guide

| Process | Blocks when | Usual fix |
|---|---|---|
| `LINT` | ESLint reports an error or any warning (`--max-warnings=0`) | Fix the rule or use `lint:fix` if safe |
| `TYPECHECK` | TypeScript reports an error | Fix the type or contract |
| `STYLES` | Stylelint reports an error | Fix the stylesheet or use `lint:styles:fix` if safe |
| `DUPLICATES` | Duplicates cross the threshold | Refactor the clone, do not add ignores |
| `DEAD-CODE` | Knip finds real dead code | Remove the dead symbol or justify the export |
| `ARCHITECTURE` | A forbidden import is found | Move the import to the right layer |
