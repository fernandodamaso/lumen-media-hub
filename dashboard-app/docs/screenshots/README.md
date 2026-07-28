# Screenshots

Captured from local Demo (`npm start`) and Storybook (`npm run storybook`) at 1920├ù1080 and 1440├ù900.

| File | Subject |
|------|---------|
| `home.png` | Nocturne ops dashboard (1920├ù1080) |
| `discover.png` | Discover page |
| `reports.png` | Reports triage |
| `storybook.png` | Current `UI/*` Storybook story (not the removed in-app catalog) |
| `theme-tokyo-night.png` | Home with Tokyo Night theme |

## Regenerate

```bash
npm run build
npx http-server dist/dashboard/browser --port 4203 --proxy http://127.0.0.1:4203?
BASE_URL=http://127.0.0.1:4203 node scripts/screenshot-review.mjs
```

Review outputs in `docs/screenshots/review/` and copy the desired captures to this folder.

Do not capture live-mode or private hostnames in committed images.
