/** @type {import('knip').KnipConfig} */
const config = {
  entry: [
    'projects/dashboard/src/app/app.config.ts!',
    'projects/dashboard/src/app/app.routes.ts!',
    'projects/dashboard/src/environments/environment*.ts!',
  ],
  project: ['projects/dashboard/src/**/*.{ts,mdx}'],
  ignoreFiles: ['.storybook/test-runner-jest.config.js'],
  ignoreDependencies: [
    '@compodoc/compodoc',
    '@eslint/js',
    'stylelint-config-standard',
  ],
  ignoreBinaries: ['magenta,blue', 'storybook-static'],
};

module.exports = config;
