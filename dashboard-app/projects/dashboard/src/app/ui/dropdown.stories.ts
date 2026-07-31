import type { Meta, StoryObj } from '@storybook/angular';
import { MmDropdown } from './dropdown';

const meta: Meta<MmDropdown> = {
  title: 'Primitives/Dropdown',
  component: MmDropdown,
  tags: ['autodocs'],
  args: {
    triggerLabel: 'Manage',
    groups: [
      {
        label: 'Library',
        items: [
          { id: 'scan', label: 'Scan disk', icon: 'scan' },
          { id: 'refresh', label: 'Refresh metadata', icon: 'refresh' },
        ],
      },
      {
        items: [{ id: 'delete', label: 'Remove files', icon: 'trash', danger: true, separatorBefore: true }],
      },
    ],
  },
};
export default meta;
type Story = StoryObj<MmDropdown>;

export const Default: Story = {};

export const Open: Story = {
  play: ({ canvasElement }) => {
    const trigger = canvasElement.querySelector<HTMLButtonElement>('.mm-dropdown__trigger');
    trigger?.click();
  },
};
