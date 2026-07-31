import { type Meta, type StoryObj } from '@storybook/angular';
import { MmStatus, type MmStatusTone } from './status';

type StatusArgs = {
  tone: MmStatusTone;
  label: string;
  announce: boolean;
  dot: boolean;
};

const meta: Meta<StatusArgs> = {
  title: 'UI/Status',
  component: MmStatus,
  tags: ['autodocs'],
  argTypes: {
    tone: {
      control: 'select',
      options: [
        'success',
        'warning',
        'danger',
        'info',
        'premiere',
        'gold',
        'green',
        'amber',
        'violet',
        'red',
        'neutral',
      ],
    },
    label: { control: 'text' },
    announce: { control: 'boolean' },
    dot: { control: 'boolean' },
  },
  args: {
    tone: 'info',
    label: 'Processing',
    announce: false,
    dot: false,
  },
  render: (args) => ({
    props: args,
    template: `<mm-status [tone]="tone" [announce]="announce" [dot]="dot">{{ label }}</mm-status>`,
  }),
};

export default meta;
type Story = StoryObj<StatusArgs>;

export const Default: Story = {
  play: ({ canvasElement }) => {
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
  play: ({ canvasElement }) => {
    const live = canvasElement.querySelectorAll('[role="status"]');
    if (live.length !== 1) throw new Error(`Expected one live region, found ${live.length}`);
    if (!live[0].classList.contains('mm-status')) {
      throw new Error('Opt-in announce must use the status chip as the live region');
    }
  },
};

/** Legacy operational tones (pre-badge merge). */
export const LegacyTones: Story = {
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
};

/** Mock badge tones from design-system.html (merged into MmStatus). */
export const BadgeTones: Story = {
  render: () => ({
    imports: [MmStatus],
    template: `<div style="display:flex;gap:10px;flex-wrap:wrap">
      <mm-status tone="gold">Continue</mm-status>
      <mm-status tone="green">New</mm-status>
      <mm-status tone="amber">Scheduled</mm-status>
      <mm-status tone="violet">Premiere</mm-status>
      <mm-status tone="red">Failed</mm-status>
      <mm-status tone="neutral">Neutral</mm-status>
    </div>`,
  }),
  play: ({ canvasElement }) => {
    for (const tone of ['gold', 'green', 'amber', 'violet', 'red', 'neutral']) {
      if (!canvasElement.querySelector(`.mm-status--${tone}`)) {
        throw new Error(`Missing badge tone: ${tone}`);
      }
    }
  },
};

export const WithDot: Story = {
  args: { tone: 'gold', label: 'Live', dot: true },
  play: ({ canvasElement }) => {
    if (!canvasElement.querySelector('.mm-status__dot')) {
      throw new Error('Dot badge must render mm-status__dot');
    }
  },
};
