import type { Meta, StoryObj } from '@storybook/angular';
import { MmProgress } from './index';

const meta = {
  title: 'UI/Progress',
  component: MmProgress,
  tags: ['autodocs'],
  parameters: { a11y: { test: 'error' } },
} satisfies Meta<typeof MmProgress>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => ({
    imports: [MmProgress],
    template: `<div style="display:grid;gap:16px;max-width:420px">
      <mm-progress [value]="0" label="Queued" />
      <mm-progress [value]="68" label="Transcoding" />
      <mm-progress [value]="100" label="Finished" />
    </div>`,
  }),
};
