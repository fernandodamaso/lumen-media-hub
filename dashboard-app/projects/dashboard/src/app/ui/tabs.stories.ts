import type { Meta, StoryObj } from '@storybook/angular';
import { MmTabs } from './tabs';

const meta: Meta<MmTabs> = {
  title: 'Primitives/Tabs',
  component: MmTabs,
  tags: ['autodocs'],
  args: {
    tabs: [
      { id: 'movies', label: 'Movies' },
      { id: 'shows', label: 'Shows' },
      { id: 'people', label: 'People' },
    ],
    active: 'movies',
  },
};
export default meta;
type Story = StoryObj<MmTabs>;

export const Default: Story = {};
