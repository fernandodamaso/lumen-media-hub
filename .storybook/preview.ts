import { provideRouter } from '@angular/router';
import { applicationConfig, type Preview } from '@storybook/angular';

function applyTheme(theme: string): void {
  document.documentElement.dataset['theme'] = theme;
  document.documentElement.style.background = 'var(--mm-semantic-surface-page)';
  document.documentElement.style.color = 'var(--mm-semantic-text-primary)';
  document.body.style.background = 'var(--mm-semantic-surface-page)';
  document.body.style.color = 'var(--mm-semantic-text-primary)';
  document.body.style.margin = '0';
  document.body.style.minHeight = '100vh';
  document.body.style.fontFamily = 'var(--mm-font-body)';
}

const preview: Preview = {
  globalTypes: {
    theme: {
      description: 'Global dashboard UI theme',
      defaultValue: 'nocturne',
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
    applicationConfig({
      providers: [provideRouter([])],
    }),
    (story, context) => {
      applyTheme(String(context.globals['theme'] ?? 'nocturne'));
      return story();
    },
  ],
  parameters: {
    a11y: { test: 'error' },
    backgrounds: { disable: true },
    controls: { expanded: true },
    layout: 'padded',
  },
};

export default preview;
