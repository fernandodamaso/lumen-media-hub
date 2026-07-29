'use strict';

const { spawnSync } = require('node:child_process');
const path = require('node:path');

const files = process.argv
  .slice(2)
  .filter((file) => /\.(ts|cts|mts|js|cjs|mjs|html)$/i.test(file));

if (files.length === 0) {
  process.exit(0);
}

const eslintRoot = path.dirname(require.resolve('eslint/package.json'));
const result = spawnSync(
  process.execPath,
  [
    path.join(eslintRoot, 'bin', 'eslint.js'),
    '--config',
    path.join(__dirname, '..', 'eslint.config.js'),
    '--no-error-on-unmatched-pattern',
    ...files,
  ],
  { stdio: 'inherit' },
);

process.exit(result.status === null ? 1 : result.status);
