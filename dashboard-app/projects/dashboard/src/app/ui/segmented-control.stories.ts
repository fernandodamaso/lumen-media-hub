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
