import type { Meta, StoryObj } from '@storybook/angular';
import { MmStatus } from './index';

const meta = {
  title: 'UI/Status',
  component: MmStatus,
  tags: ['autodocs'],
  parameters: { a11y: { test: 'error' } },
} satisfies Meta<typeof MmStatus>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Tones: Story = {
  render: () => ({
    imports: [MmStatus],
    template: `<div style="display:flex;gap:10px;flex-wrap:wrap">
      <mm-status tone="success">Ready</mm-status>
      <mm-status tone="warning">Needs review</mm-status>
      <mm-status tone="danger">Failed</mm-status>
      <mm-status tone="info">Processing</mm-status>
    </div>`,
  }),
  play: async ({ canvasElement }) => {
    const statuses = canvasElement.querySelectorAll('[role="status"]');
    if (statuses.length !== 4) throw new Error(`Expected 4 status chips, found ${statuses.length}`);
    for (const tone of ['success', 'warning', 'danger', 'info']) {
      if (!canvasElement.querySelector(`.mm-status--${tone}`)) {
        throw new Error(`Missing status tone: ${tone}`);
      }
    }
  },
};
