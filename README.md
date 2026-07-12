# Media Manager Angular

Runnable Angular 22 workspace for the Media Manager shell. It contains the standalone `dashboard` application and the `media-ui` component library.

## Local development

```bash
npm ci
npm start
```

Open `http://localhost:4200/`. The shell supports `/`, `/dashboard`, `/reports`, `/discover`, and `/ui`.

## Verification

```bash
npm run lint
npm test -- --watch=false
npm run build:dashboard
npm run build:media-ui
```

The dashboard uses Angular's standard history-based router. Configure the host to fall back to `index.html` for direct navigation in production.
