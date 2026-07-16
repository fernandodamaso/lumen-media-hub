import { type Meta, type StoryObj } from '@storybook/angular';
import { MmStatus } from './index';

type StatusArgs = {
  tone: 'success' | 'warning' | 'danger' | 'info';
  label: string;
};

const meta: Meta<StatusArgs> = {
  title: 'UI/Status',
  component: MmStatus,
  tags: ['autodocs'],
  argTypes: {
    tone: {
      control: 'select',
      options: ['success', 'warning', 'danger', 'info'],
    },
    label: { control: 'text' },
  },
  args: {
    tone: 'info',
    label: 'Processing',
  },
  render: (args) => ({
    props: args,
    template: `<mm-status [tone]="tone">{{ label }}</mm-status>`,
  }),
};

export default meta;
type Story = StoryObj<StatusArgs>;

export const Default: Story = {};

export const Success: Story = {
  args: { tone: 'success', label: 'Ready' },
};

export const Warning: Story = {
  args: { tone: 'warning', label: 'Needs review' },
};

export const Danger: Story = {
  args: { tone: 'danger', label: 'Failed' },
};

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
