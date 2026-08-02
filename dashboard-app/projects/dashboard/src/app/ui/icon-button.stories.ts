import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { LucidePause, LucidePlay, LucideRefreshCw } from '@lucide/angular';
import { MmIconButton } from './index';

type IconButtonArgs = {
  label: string;
  disabled: boolean;
  busy: boolean;
  size: 'sm' | 'md';
  shape: 'rounded' | 'circle';
};

const meta: Meta<IconButtonArgs> = {
  title: 'UI/IconButton',
  component: MmIconButton,
  tags: ['autodocs'],
  argTypes: {
    label: { control: 'text' },
    disabled: { control: 'boolean' },
    busy: { control: 'boolean' },
    size: { control: 'inline-radio', options: ['sm', 'md'] },
    shape: { control: 'inline-radio', options: ['rounded', 'circle'] },
  },
  args: {
    label: 'Refresh',
    disabled: false,
    busy: false,
    size: 'md',
    shape: 'rounded',
  },
  render: (args) => ({
    props: args,
    moduleMetadata: { imports: [LucideRefreshCw] },
    template: `<mm-icon-button ${argsToTemplate(args)}>
      <svg lucideRefreshCw [size]="16" aria-hidden="true"></svg>
    </mm-icon-button>`,
  }),
};

export default meta;
type Story = StoryObj<IconButtonArgs>;

export const Default: Story = {};

export const Busy: Story = {
  args: { label: 'Refreshing', busy: true },
};

export const Disabled: Story = {
  args: { label: 'Unavailable', disabled: true },
};

export const SmallCircle: Story = {
  args: { label: 'Previous', size: 'sm', shape: 'circle' },
};

export const MediumRounded: Story = {
  args: { label: 'Refresh', size: 'md', shape: 'rounded' },
};

export const PauseResume: Story = {
  render: () => ({
    moduleMetadata: { imports: [MmIconButton, LucidePause, LucidePlay] },
    template: `<div style="display:flex;gap:12px">
      <mm-icon-button label="Pause Afterlight">
        <svg lucidePause [size]="16" aria-hidden="true"></svg>
      </mm-icon-button>
      <mm-icon-button label="Resume Afterlight">
        <svg lucidePlay [size]="16" aria-hidden="true"></svg>
      </mm-icon-button>
    </div>`,
  }),
  play: ({ canvasElement }) => {
    const buttons = canvasElement.querySelectorAll('button[aria-label]');
    if (buttons.length !== 2) throw new Error(`Expected 2 icon buttons, found ${buttons.length}`);
  },
};
