# Quality gates

## Scripts

| Script | When | What |
|---|---|---|
| `lint` / `lint:styles` / `lint:agent` | Day-to-day / idle agent | Fast checks (non-typed ESLint) |
| `quality:commit` | **git pre-commit** | Typed ESLint + `tsc` + Stylelint |
| `quality` | **git pre-push** | Commit gate + duplication + dead code + architecture |

## Git hooks

Checked in under `githooks/`. Install with:

```bash
npm run hooks:install
```

`prepare` runs the same on `npm install`. This sets `core.hooksPath=githooks` for this repo only.

- `pre-commit` → `npm run quality:commit`
- `pre-push` → `npm run quality`
