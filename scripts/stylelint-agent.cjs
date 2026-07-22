'use strict';

const { spawnSync } = require('node:child_process');
const path = require('node:path');

const files = process.argv
  .slice(2)
  .filter((file) => /\.(css|scss|sass|less)$/i.test(file));

if (files.length === 0) {
  process.exit(0);
}

const stylelintRoot = path.dirname(require.resolve('stylelint/package.json'));
const result = spawnSync(
  process.execPath,
  [
    path.join(stylelintRoot, 'bin', 'stylelint.mjs'),
    '--config',
    path.join(__dirname, '..', 'stylelint.config.js'),
    '--allow-empty-input',
    ...files,
  ],
  { stdio: 'inherit' },
);

process.exit(result.status === null ? 1 : result.status);
