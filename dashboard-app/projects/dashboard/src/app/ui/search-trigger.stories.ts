import type { Meta, StoryObj } from '@storybook/angular';
import { MmSearchTrigger } from './search-trigger';

const meta: Meta<MmSearchTrigger> = {
  title: 'UI/Search Trigger',
  component: MmSearchTrigger,
  tags: ['autodocs'],
};
export default meta;
type Story = StoryObj<MmSearchTrigger>;

export const Default: Story = {
  args: {
    placeholder: 'Search movies, shows, people…',
    shortcutLabel: 'Ctrl+K',
    ariaLabel: 'Open search',
  },
};

export const Disabled: Story = {
  args: {
    placeholder: 'Search unavailable',
    shortcutLabel: 'Ctrl+K',
    disabled: true,
  },
};
