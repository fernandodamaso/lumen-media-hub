const { getJestConfig } = require('@storybook/test-runner');

const testRunnerConfig = getJestConfig();

/** @type {import('@jest/types').Config.InitialOptions} */
module.exports = {
  ...testRunnerConfig,
  // Absolute STORYBOOK_STORIES_PATTERN paths fail Jest matching in nested worktrees on Windows.
  roots: ['<rootDir>/projects/dashboard/src/app'],
  testMatch: ['**/*.stories.ts'],
};
