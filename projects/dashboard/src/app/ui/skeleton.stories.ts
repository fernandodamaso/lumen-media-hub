import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MmSkeleton, type MmSkeletonVariant } from './index';

type SkeletonArgs = {
  variant: MmSkeletonVariant;
  width?: string;
  height?: string;
};

const meta: Meta<SkeletonArgs> = {
  title: 'UI/Skeleton',
  component: MmSkeleton,
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['text', 'rect', 'circle'],
    },
    width: { control: 'text' },
    height: { control: 'text' },
  },
  args: {
    variant: 'text',
  },
  render: (args) => ({
    props: args,
    template: `<div style="max-width:320px"><mm-skeleton ${argsToTemplate(args)} /></div>`,
  }),
};

export default meta;
type Story = StoryObj<SkeletonArgs>;

export const Text: Story = {};

export const NarrowText: Story = {
  args: { variant: 'text', width: '70%' },
};

export const Rect: Story = {
  args: { variant: 'rect', width: '180px', height: '120px' },
};

export const Circle: Story = {
  args: { variant: 'circle', width: '48px', height: '48px' },
};

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
  play: ({ canvasElement }) => {
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
