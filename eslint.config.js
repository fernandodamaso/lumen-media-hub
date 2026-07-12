/* eslint-disable @typescript-eslint/no-require-imports */
const tseslint = require('typescript-eslint');

module.exports = [
  { ignores: ['dist/**', '.angular/**', 'node_modules/**'] },
  ...tseslint.configs.recommended,
  {
    files: ['**/*.ts'],
    languageOptions: { parserOptions: { projectService: true } },
    rules: {
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['eslint.config.js'],
    languageOptions: { globals: { require: 'readonly', module: 'readonly' } },
  },
];
