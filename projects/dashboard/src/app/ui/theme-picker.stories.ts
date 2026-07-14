import type { Meta, StoryObj } from '@storybook/angular';
import { MmThemePicker } from './index';

const meta = {
  title: 'UI/ThemePicker',
  component: MmThemePicker,
  tags: ['autodocs'],
  parameters: { a11y: { test: 'error' } },
} satisfies Meta<typeof MmThemePicker>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => ({ imports: [MmThemePicker], template: '<mm-theme-picker />' }),
};

export const ChangesTheme: Story = {
  render: () => ({ imports: [MmThemePicker], template: '<mm-theme-picker />' }),
  play: async ({ canvasElement }) => {
    const select = canvasElement.querySelector<HTMLSelectElement>('select[aria-label="Choose theme"]');
    if (!select) throw new Error('Theme picker select was not rendered');
    select.value = 'tokyo-night';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    if (select.value !== 'tokyo-night') throw new Error('Theme selection did not update');
    if (document.documentElement.dataset['theme'] !== 'tokyo-night') {
      throw new Error('Theme was not applied to documentElement');
    }
    if (localStorage.getItem('media-ui-theme') !== 'tokyo-night') {
      throw new Error('Theme was not persisted to localStorage');
    }
  },
};
