'use strict';

const { chmodSync, existsSync } = require('node:fs');
const { execSync, spawnSync } = require('node:child_process');
const path = require('node:path');

const dashboardApp = path.resolve(__dirname, '..');
const hooksDir = path.join(dashboardApp, 'githooks');
const preCommit = path.join(hooksDir, 'pre-commit');

let gitRoot;
try {
  gitRoot = execSync('git rev-parse --show-toplevel', {
    cwd: dashboardApp,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'ignore'],
  }).trim();
} catch {
  process.exit(0);
}

const hooksPath = path.relative(gitRoot, hooksDir).split(path.sep).join('/');
const result = spawnSync('git', ['config', 'core.hooksPath', hooksPath], {
  cwd: gitRoot,
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
