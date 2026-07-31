import type { Meta, StoryObj } from '@storybook/angular';
import { MmSlider } from './slider';

const meta: Meta<MmSlider> = {
  title: 'Primitives/Slider',
  component: MmSlider,
  tags: ['autodocs'],
  render: (args) => ({
    props: args,
    template: `<div style="width:280px"><mm-slider [value]="value" [min]="0" [max]="100" /></div>`,
  }),
};
export default meta;
type Story = StoryObj<MmSlider>;

export const Default: Story = { args: { value: 62 } };
