import type { Meta, StoryObj } from '@storybook/angular';
import { Topbar } from './topbar';

const meta: Meta<Topbar> = {
  title: 'Shell/Topbar',
  component: Topbar,
  tags: ['autodocs'],
  args: { shortcutLabel: 'Ctrl+K' },
};
export default meta;
type Story = StoryObj<Topbar>;

export const Default: Story = {};

export const MacShortcut: Story = {
  args: { shortcutLabel: '⌘K' },
};
