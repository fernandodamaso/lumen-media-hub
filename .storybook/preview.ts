import type { Preview } from '@storybook/angular';

const preview: Preview = {
  globalTypes: {
    theme: {
      description: 'Global dashboard UI theme',
      defaultValue: 'github-dark-pro',
      toolbar: {
        icon: 'paintbrush',
        items: [
          { value: 'nocturne', title: 'Nocturne' },
          { value: 'tokyo-night', title: 'Tokyo Night' },
          { value: 'github-dark-pro', title: 'GitHub Dark Pro' },
        ],
      },
    },
  },
  decorators: [
    (story, context) => {
      document.documentElement.dataset['theme'] = context.globals['theme'];
      return story();
    },
  ],
  parameters: {
    a11y: { test: 'error' },
    controls: { expanded: true },
  },
};

export default preview;
