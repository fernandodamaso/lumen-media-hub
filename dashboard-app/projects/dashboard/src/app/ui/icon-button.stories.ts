import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { LucidePause, LucidePlay, LucideRefreshCw } from '@lucide/angular';
import { MmIconButton } from './index';

type IconButtonArgs = {
  label: string;
  disabled: boolean;
  busy: boolean;
  size: 'sm' | 'md';
  shape: 'rounded' | 'circle';
  tone: 'default' | 'danger';
  surface: 'default' | 'overlay';
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
    tone: { control: 'inline-radio', options: ['default', 'danger'] },
    surface: { control: 'inline-radio', options: ['default', 'overlay'] },
  },
  args: {
    label: 'Refresh',
    disabled: false,
    busy: false,
    size: 'md',
    shape: 'rounded',
    tone: 'default',
    surface: 'default',
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

export const Danger: Story = {
  args: { label: 'Delete', tone: 'danger' },
  play: ({ canvasElement }) => {
    const button = canvasElement.querySelector('button.mm-icon-button--danger');
    if (!button) throw new Error('Danger icon button is missing its tone class');
  },
};

export const Overlay: Story = {
  args: { label: 'Mark watched', surface: 'overlay' },
  play: ({ canvasElement }) => {
    const button = canvasElement.querySelector('button.mm-icon-button--overlay');
    if (!button) throw new Error('Overlay icon button is missing its surface class');
  },
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
