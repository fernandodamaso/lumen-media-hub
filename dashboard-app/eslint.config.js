const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');
const sonarjs = require('eslint-plugin-sonarjs');

/**
 * Fast day-to-day / agent profile.
 * Strict typed lint lives in eslint.typed.config.js and powers `npm run lint`.
 */
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
      'scripts/**',
      'eslint.config.js',
      'eslint.typed.config.js',
      'stylelint.config.js',
      'knip.config.cjs',
      '.dependency-cruiser.cjs',
      'playwright.config.ts',
    ],
  },
  {
    files: ['**/*.ts'],
    extends: [
      ...tseslint.configs.recommended,
      ...angular.configs.tsRecommended,
      sonarjs.configs.recommended,
    ],
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

      // Angular inject() + kickoff in constructors is intentional here.
      'sonarjs/no-async-constructor': 'off',

      // Idle/agent: warn on smells so fixes stay focused.
      'sonarjs/cognitive-complexity': ['warn', 15],
      'sonarjs/no-identical-functions': 'warn',
      'sonarjs/no-duplicate-string': ['warn', { threshold: 5 }],
      'sonarjs/no-duplicated-branches': 'error',
      'sonarjs/no-all-duplicated-branches': 'error',
      'sonarjs/no-identical-expressions': 'error',
    },
  },
  {
    files: ['**/*.{spec,stories}.ts', '**/mock-*.ts'],
    rules: {
      'sonarjs/no-clear-text-protocols': 'off',
      'sonarjs/no-duplicate-string': 'off',
      'sonarjs/no-identical-functions': 'off',
    },
  },
  {
    files: ['**/app/app.ts'],
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
);
