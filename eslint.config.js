const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');

module.exports = tseslint.config(
  {
    ignores: [
      'dist/**',
      '.angular/**',
      'node_modules/**',
      '.storybook/**',
      'storybook-static/**',
      '.worktrees/**',
      '**/.worktrees/**',
      'docs/mockups/**',
    ],
  },
  {
    files: ['**/*.ts'],
    extends: [...tseslint.configs.recommended, ...angular.configs.tsRecommended],
    languageOptions: { parserOptions: { projectService: true } },
    processor: angular.processInlineTemplates,
    rules: {
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      '@angular-eslint/directive-selector': [
        'error',
        { type: 'attribute', prefix: 'mm', style: 'camelCase' },
      ],
      '@angular-eslint/component-selector': [
        'error',
        { type: 'element', prefix: 'mm', style: 'kebab-case' },
      ],
      '@angular-eslint/prefer-on-push-component-change-detection': 'error',
    },
  },
  {
    // Bootstrap host: Angular requires `app-root`; feature components use `mm-`.
    files: ['projects/dashboard/src/app/app.ts'],
    rules: {
      '@angular-eslint/component-selector': [
        'error',
        { type: 'element', prefix: 'app', style: 'kebab-case' },
      ],
    },
  },
  {
    files: ['**/*.html'],
    extends: [
      ...angular.configs.templateRecommended,
      ...angular.configs.templateAccessibility,
    ],
  },
  {
    files: ['eslint.config.js'],
    languageOptions: { globals: { require: 'readonly', module: 'readonly' } },
  },
);
