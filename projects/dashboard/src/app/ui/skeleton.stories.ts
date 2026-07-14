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
  play: async ({ canvasElement }) => {
    const skeletons = canvasElement.querySelectorAll('.mm-skeleton');
    if (skeletons.length !== 4) throw new Error(`Expected 4 skeletons, found ${skeletons.length}`);
    for (const skeleton of skeletons) {
      if (skeleton.getAttribute('aria-hidden') !== 'true') {
        throw new Error('Skeleton placeholders must be aria-hidden');
      }
    }
    if (!canvasElement.querySelector('.mm-skeleton--text')) throw new Error('Missing text skeleton');
    if (!canvasElement.querySelector('.mm-skeleton--rect')) throw new Error('Missing rect skeleton');
    if (!canvasElement.querySelector('.mm-skeleton--circle')) throw new Error('Missing circle skeleton');
  },
};
