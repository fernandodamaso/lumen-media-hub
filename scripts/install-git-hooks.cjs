'use strict';

const { existsSync } = require('node:fs');
const { spawnSync } = require('node:child_process');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const gitDir = path.join(root, '.git');
const hooksPath = 'githooks';

if (!existsSync(gitDir)) {
  process.exit(0);
}

const result = spawnSync('git', ['config', 'core.hooksPath', hooksPath], {
  cwd: root,
  stdio: 'inherit',
  shell: process.platform === 'win32',
});

process.exit(result.status === null ? 1 : result.status);
