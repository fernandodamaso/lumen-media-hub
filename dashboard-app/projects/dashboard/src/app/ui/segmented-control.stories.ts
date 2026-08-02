import type { Meta, StoryObj } from '@storybook/angular';
import { MmSegmentedControl } from './segmented-control';

const meta: Meta<MmSegmentedControl> = {
  title: 'UI/SegmentedControl',
  component: MmSegmentedControl,
  tags: ['autodocs'],
  args: {
    options: [
      { value: 'all', label: 'All' },
      { value: 'movies', label: 'Movies' },
      { value: 'series', label: 'Series' },
    ],
    value: 'all',
    label: 'Library filter',
    size: 'md',
  },
};

export default meta;
type Story = StoryObj<MmSegmentedControl>;

export const Default: Story = {};
export const Small: Story = { args: { size: 'sm' } };

export const LongLabels: Story = {
  args: {
    options: [
      { value: 'all', label: 'All available media' },
      { value: 'movies', label: 'Feature films and premieres' },
      { value: 'series', label: 'Series and episodic collections' },
    ],
    value: 'movies',
  },
};

export const SelectedState: Story = {
  args: { value: 'series' },
  play: ({ canvasElement }) => {
    const selected = canvasElement.querySelector('[role="radio"][aria-checked="true"]');
    if (!selected || selected.textContent.trim() !== 'Series') throw new Error('Series should be selected');
  },
};

export const KeyboardNavigation: Story = {
  play: async ({ canvasElement }) => {
    const options = [...canvasElement.querySelectorAll<HTMLButtonElement>('[role="radio"]')];
    const firstOption = options[0];
    const lastOption = options[options.length - 1];
    firstOption.focus();
    firstOption.dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true }));
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    if (document.activeElement?.isSameNode(lastOption) !== true) throw new Error('End should move focus to the last option');
    if (lastOption.getAttribute('aria-checked') !== 'true') throw new Error('End should select the last option');
  },
};
