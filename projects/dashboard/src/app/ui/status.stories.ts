import { type Meta, type StoryObj } from '@storybook/angular';
import { MmStatus } from './index';

type StatusArgs = {
  tone: 'success' | 'warning' | 'danger' | 'info' | 'premiere';
  label: string;
  announce: boolean;
};

const meta: Meta<StatusArgs> = {
  title: 'UI/Status',
  component: MmStatus,
  tags: ['autodocs'],
  argTypes: {
    tone: {
      control: 'select',
      options: ['success', 'warning', 'danger', 'info', 'premiere'],
    },
    label: { control: 'text' },
    announce: { control: 'boolean' },
  },
  args: {
    tone: 'info',
    label: 'Processing',
    announce: false,
  },
  render: (args) => ({
    props: args,
    template: `<mm-status [tone]="tone" [announce]="announce">{{ label }}</mm-status>`,
  }),
};

export default meta;
type Story = StoryObj<StatusArgs>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    const status = canvasElement.querySelector('.mm-status');
    if (!status) throw new Error('Status was not rendered');
    if (status.getAttribute('role') === 'status') {
      throw new Error('Default status must not create a live region');
    }
  },
};

export const Success: Story = {
  args: { tone: 'success', label: 'Ready' },
};

export const Warning: Story = {
  args: { tone: 'warning', label: 'Needs review' },
};

export const Danger: Story = {
  args: { tone: 'danger', label: 'Failed' },
};

export const Announcing: Story = {
  args: { tone: 'warning', label: 'Queue updated', announce: true },
  play: async ({ canvasElement }) => {
    const live = canvasElement.querySelectorAll('[role="status"]');
    if (live.length !== 1) throw new Error(`Expected one live region, found ${live.length}`);
    if (!live[0]?.classList.contains('mm-status')) {
      throw new Error('Opt-in announce must use the status chip as the live region');
    }
  },
};

export const Tones: Story = {
  render: () => ({
    imports: [MmStatus],
    template: `<div style="display:flex;gap:10px;flex-wrap:wrap">
      <mm-status tone="success">Ready</mm-status>
      <mm-status tone="warning">Needs review</mm-status>
      <mm-status tone="danger">Failed</mm-status>
      <mm-status tone="info">Processing</mm-status>
      <mm-status tone="premiere">Premiere</mm-status>
    </div>`,
  }),
  play: async ({ canvasElement }) => {
    const statuses = canvasElement.querySelectorAll('.mm-status');
    if (statuses.length !== 5) throw new Error(`Expected 5 status chips, found ${statuses.length}`);
    if (canvasElement.querySelectorAll('[role="status"]').length !== 0) {
      throw new Error('Neutral status gallery must not create live regions');
    }
    for (const tone of ['success', 'warning', 'danger', 'info', 'premiere']) {
      if (!canvasElement.querySelector(`.mm-status--${tone}`)) {
        throw new Error(`Missing status tone: ${tone}`);
      }
    }
  },
};
