import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MmProgress } from './index';

type ProgressArgs = {
  value: number;
  label: string;
};

const meta: Meta<ProgressArgs> = {
  title: 'UI/Progress',
  component: MmProgress,
  tags: ['autodocs'],
  argTypes: {
    value: { control: { type: 'range', min: 0, max: 100, step: 1 } },
    label: { control: 'text' },
  },
  args: {
    value: 68,
    label: 'Transcoding',
  },
  render: (args) => ({
    props: args,
    template: `<div style="max-width:420px"><mm-progress ${argsToTemplate(args)} /></div>`,
  }),
};

export default meta;
type Story = StoryObj<ProgressArgs>;

export const Default: Story = {};

export const Queued: Story = {
  args: { value: 0, label: 'Queued' },
};

export const Finished: Story = {
  args: { value: 100, label: 'Finished' },
};

export const Values: Story = {
  render: () => ({
    imports: [MmProgress],
    template: `<div style="display:grid;gap:16px;max-width:420px">
      <mm-progress [value]="0" label="Queued" />
      <mm-progress [value]="68" label="Transcoding" />
      <mm-progress [value]="100" label="Finished" />
    </div>`,
  }),
  play: ({ canvasElement }) => {
    const bars = canvasElement.querySelectorAll('[role="progressbar"]');
    if (bars.length !== 3) throw new Error(`Expected 3 progress bars, found ${bars.length}`);
    const values = [...bars].map((bar) => bar.getAttribute('aria-valuenow'));
    if (values.join(',') !== '0,68,100') {
      throw new Error(`Unexpected progress values: ${values.join(',')}`);
    }
    if (bars[1].getAttribute('aria-label') !== 'Transcoding') {
      throw new Error('Transcoding progress is missing its accessible label');
    }
  },
};
