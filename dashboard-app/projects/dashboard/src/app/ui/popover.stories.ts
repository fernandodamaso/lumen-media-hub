import type { Meta, StoryObj } from '@storybook/angular';
import { MmPopover } from './popover';

const meta: Meta<MmPopover> = {
  title: 'Primitives/Popover',
  component: MmPopover,
  tags: ['autodocs'],
  render: () => ({
    template: `
      <div style="display:grid;place-items:center;padding:140px 40px 60px">
        <mm-popover triggerLabel="Show info">
          <p style="margin:0">Radarr grabbed a new release for Frontline (2026).</p>
        </mm-popover>
      </div>
    `,
  }),
};
export default meta;
type Story = StoryObj;

export const Default: Story = {};

export const Open: Story = {
  play: ({ canvasElement }) => {
    const trigger = canvasElement.querySelector<HTMLButtonElement>('.mm-popover__trigger');
    trigger?.click();
  },
};
