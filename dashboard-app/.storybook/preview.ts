import { provideRouter } from '@angular/router';
import { applicationConfig, type Preview } from '@storybook/angular';

function applySurface(): void {
  document.documentElement.style.background = 'var(--mm-semantic-surface-page)';
  document.documentElement.style.color = 'var(--mm-semantic-text-primary)';
  document.body.style.background = 'var(--mm-semantic-surface-page)';
  document.body.style.color = 'var(--mm-semantic-text-primary)';
  document.body.style.margin = '0';
  document.body.style.minHeight = '100vh';
  document.body.style.fontFamily = 'var(--mm-font-body)';
}

const preview: Preview = {
  decorators: [
    applicationConfig({
      providers: [provideRouter([])],
    }),
    (story) => {
      applySurface();
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
