import type { Meta, StoryObj } from '@storybook/angular';
import { MmSkeleton } from './index';

const meta = {
  title: 'UI/Skeleton',
  component: MmSkeleton,
  tags: ['autodocs'],
  parameters: { a11y: { test: 'error' } },
} satisfies Meta<typeof MmSkeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Variants: Story = {
  render: () => ({
    imports: [MmSkeleton],
    template: `<div style="display:grid;gap:16px;max-width:320px">
      <mm-skeleton variant="text" />
      <mm-skeleton variant="text" width="70%" />
      <mm-skeleton variant="rect" width="180px" height="120px" />
      <mm-skeleton variant="circle" width="48px" height="48px" />
    </div>`,
  }),
};
