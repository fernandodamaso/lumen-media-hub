import { type Meta, type StoryObj } from '@storybook/angular';
import { MmThemePicker } from './index';

const meta: Meta = {
  title: 'UI/ThemePicker',
  component: MmThemePicker,
  tags: ['autodocs'],
  render: () => ({
    imports: [MmThemePicker],
    template: '<mm-theme-picker />',
  }),
};

export default meta;
type Story = StoryObj;

async function waitForThemeApplied(): Promise<void> {
  const deadline = Date.now() + 1000;
  while (Date.now() < deadline) {
    if (
      document.documentElement.dataset['theme'] === 'tokyo-night' &&
      localStorage.getItem('media-ui-theme') === 'tokyo-night'
    ) {
      return;
    }
    const { promise, resolve } = Promise.withResolvers<undefined>();
    setTimeout(() => {
      resolve(undefined);
    }, 10);
    await promise;
  }
  if (document.documentElement.dataset['theme'] !== 'tokyo-night') {
    throw new Error('Theme was not applied to documentElement');
  }
  if (localStorage.getItem('media-ui-theme') !== 'tokyo-night') {
    throw new Error('Theme was not persisted to localStorage');
  }
}

export const Default: Story = {};

export const ChangesTheme: Story = {
  play: async ({ canvasElement }) => {
    const group = canvasElement.querySelector<HTMLElement>('[role="group"][aria-label="Choose theme"]');
    if (!group) throw new Error('Theme picker was not rendered');
    const tokyo = [...group.querySelectorAll('button')].find(
      (button) => button.getAttribute('title') === 'Tokyo Night' || button.textContent.includes('Tokyo Night'),
    );
    if (!tokyo) throw new Error('Tokyo Night theme button was not rendered');
    tokyo.click();
    await waitForThemeApplied();
  },
};
