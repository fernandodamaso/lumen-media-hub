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
          { id: 'scan', label: 'Scan disk' },
          { id: 'refresh', label: 'Refresh metadata' },
        ],
      },
      {
        items: [{ id: 'delete', label: 'Remove files', danger: true, separatorBefore: true }],
      },
    ],
  },
};
export default meta;
type Story = StoryObj<MmDropdown>;

export const Default: Story = {};
