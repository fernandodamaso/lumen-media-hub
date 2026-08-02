const recommended = require('./node_modules/dependency-cruiser/configs/recommended.cjs');

/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    // Knip owns unused-code detection, so keep Dependency Cruiser focused on architecture.
    ...recommended.forbidden.filter((r) => r.name !== 'no-orphans'),
    {
      name: 'ui-not-to-features-or-api',
      comment:
        'Design-system primitives (app/ui) must not depend on feature folders or media-stack.',
      severity: 'error',
      from: { path: '(^|/)app/ui/' },
      to: {
        path: '(^|/)app/(automation|calendar|dashboard|discover|downloads|library|reports|storage|media-stack)/',
      },
    },
    {
      name: 'media-stack-not-to-ui',
      comment:
        'Transport/API boundary must not depend on UI primitives. Feature domain/format imports are allowed for wire mapping.',
      severity: 'error',
      from: { path: '(^|/)app/media-stack/' },
      to: { path: '(^|/)app/ui/' },
    },
    {
      name: 'features-not-to-dashboard',
      comment:
        'Dashboard is the home composition root; other features must not import it.',
      severity: 'error',
      from: {
        path: '(^|/)app/(automation|calendar|discover|downloads|library|reports|storage)/',
      },
      to: { path: '(^|/)app/dashboard/' },
    },
    {
      name: 'not-to-specs-or-stories',
      comment: 'Production source must not import test or Storybook modules.',
      severity: 'error',
      from: {
        pathNot: '\\.(spec|stories)\\.ts$',
      },
      to: {
        path: '\\.(spec|stories)\\.ts$',
      },
    },
  ],
  options: {
    ...recommended.options,
    tsConfig: {
      fileName: 'tsconfig.json',
    },
    tsPreCompilationDeps: true,
    enhancedResolveOptions: {
      exportsFields: ['exports'],
      conditionNames: ['import', 'require', 'node', 'default'],
      mainFields: ['module', 'main', 'types', 'typings'],
    },
    exclude: {
      path: [
        'node_modules',
        '\\.angular',
        'dist',
        'storybook-static',
        '\\.worktrees',
        '\\.spec\\.ts$',
        '\\.stories\\.ts$',
      ],
    },
  },
};
