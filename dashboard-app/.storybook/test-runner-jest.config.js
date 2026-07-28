const path = require('path');
const { getJestConfig } = require('@storybook/test-runner');

const testRunnerConfig = getJestConfig();
const dashboardAppRoot = path.join(__dirname, '..');
const storyRoots = path.join(dashboardAppRoot, 'projects/dashboard/src/app');

/** @type {import('@jest/types').Config.InitialOptions} */
module.exports = {
  ...testRunnerConfig,
  rootDir: dashboardAppRoot,
  // Resolve from dashboard-app root (CI working-directory and local npm scripts).
  roots: [storyRoots],
  testMatch: ['**/*.stories.ts'],
};
