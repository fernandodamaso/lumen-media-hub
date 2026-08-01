import { componentWrapperDecorator } from '@storybook/angular';
import type { Meta, StoryObj } from '@storybook/angular';
import { Topbar } from './topbar';

const meta: Meta<Topbar> = {
  title: 'Shell/Topbar',
  component: Topbar,
  tags: ['autodocs'],
  args: { shortcutLabel: 'Ctrl+K' },
  decorators: [componentWrapperDecorator((story) => `<div><div id="activity-rail" hidden></div>${story}</div>`)],
};
export default meta;
type Story = StoryObj<Topbar>;

export const Default: Story = {};

export const MacShortcut: Story = {
  args: { shortcutLabel: '⌘K' },
};
