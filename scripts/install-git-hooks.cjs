'use strict';

const { chmodSync, existsSync } = require('node:fs');
const { spawnSync } = require('node:child_process');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const gitDir = path.join(root, '.git');
const hooksPath = 'githooks';
const preCommit = path.join(root, hooksPath, 'pre-commit');

if (!existsSync(gitDir)) {
  process.exit(0);
}

const result = spawnSync('git', ['config', 'core.hooksPath', hooksPath], {
  cwd: root,
  stdio: 'inherit',
  shell: process.platform === 'win32',
});

if (result.status !== 0) {
  process.exit(result.status === null ? 1 : result.status);
}

if (existsSync(preCommit)) {
  chmodSync(preCommit, 0o755);
}

process.exit(0);
