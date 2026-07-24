/** @type {import('stylelint').Config} */
module.exports = {
  extends: ['stylelint-config-standard-scss'],
  ignoreFiles: [
    '**/node_modules/**',
    '**/dist/**',
    '**/.angular/**',
    '**/storybook-static/**',
    '**/.worktrees/**',
    '**/docs/mockups/**',
    '**/docs/Kimi_Agent_Angular Media App UI Improvements/**',
  ],
  rules: {
    // Existing styles use BEM (`block__element--modifier`).
    'selector-class-pattern': [
      '^[a-z]([a-z0-9-]+)?(__([a-z0-9]+-?)+)?(--([a-z0-9]+-?)+)?$',
      {
        message: 'Expected class selector to be kebab-case or BEM',
      },
    ],
    // Angular component SCSS commonly uses compact single-line rules and tight grouping.
    'declaration-block-single-line-max-declarations': null,
    'rule-empty-line-before': null,
    'at-rule-empty-line-before': null,
    'custom-property-empty-line-before': null,
    // Prefer keeping existing `@use '...scss'` and `max-width` media queries.
    'scss/load-partial-extension': null,
    'media-feature-range-notation': null,
    // Avoid false positives on CSS font shorthand `size/line-height`.
    'scss/operator-no-unspaced': null,
    // Allow Angular-oriented / vendor patterns already in the codebase.
    'selector-pseudo-element-no-unknown': [
      true,
      { ignorePseudoElements: ['ng-deep'] },
    ],
    'property-no-vendor-prefix': null,
    'value-keyword-case': [
      'lower',
      { ignoreKeywords: ['BlinkMacSystemFont', 'Helvetica Neue'] },
    ],
  },
};
