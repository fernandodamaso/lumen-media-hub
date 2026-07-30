import type { Meta, StoryObj } from '@storybook/angular';
import { MmPopover } from './popover';

const meta: Meta<MmPopover> = {
  title: 'Primitives/Popover',
  component: MmPopover,
  tags: ['autodocs'],
  render: () => ({
    template: `
      <mm-popover triggerLabel="Show info">
        <p style="margin:0">Radarr grabbed a new release for Frontline (2026).</p>
      </mm-popover>
    `,
  }),
};
export default meta;
type Story = StoryObj;

export const Default: Story = {};
