import type { StorybookConfig } from '@storybook/angular';

const config: StorybookConfig = {
  stories: ['../projects/media-ui/src/**/*.stories.ts'],
  addons: ['@storybook/addon-a11y', '@storybook/addon-docs'],
  framework: {
    name: '@storybook/angular',
    options: { compodoc: true, compodocArgs: ['-e', 'json', '-d', '.'] },
  },
};

export default config;
