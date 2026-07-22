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

export const Default: Story = {};

async function waitForThemeApplied(select: HTMLSelectElement): Promise<void> {
  const deadline = Date.now() + 1000;
  while (Date.now() < deadline) {
    if (
      select.value === 'tokyo-night' &&
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
  if (select.value !== 'tokyo-night') throw new Error('Theme selection did not update');
  if (document.documentElement.dataset['theme'] !== 'tokyo-night') {
    throw new Error('Theme was not applied to documentElement');
  }
  if (localStorage.getItem('media-ui-theme') !== 'tokyo-night') {
    throw new Error('Theme was not persisted to localStorage');
  }
}

export const ChangesTheme: Story = {
  play: async ({ canvasElement }) => {
    const select = canvasElement.querySelector<HTMLSelectElement>('select[aria-label="Choose theme"]');
    if (!select) throw new Error('Theme picker select was not rendered');
    select.value = 'tokyo-night';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    await waitForThemeApplied(select);
  },
};
