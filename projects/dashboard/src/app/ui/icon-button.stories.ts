import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { LucidePause, LucidePlay, LucideRefreshCw } from '@lucide/angular';
import { MmIconButton } from './index';

type IconButtonArgs = {
  label: string;
  disabled: boolean;
  busy: boolean;
};

const meta: Meta<IconButtonArgs> = {
  title: 'UI/IconButton',
  component: MmIconButton,
  tags: ['autodocs'],
  argTypes: {
    label: { control: 'text' },
    disabled: { control: 'boolean' },
    busy: { control: 'boolean' },
  },
  args: {
    label: 'Refresh',
    disabled: false,
    busy: false,
  },
  render: (args) => ({
    props: args,
    moduleMetadata: { imports: [LucideRefreshCw] },
    template: `<mm-icon-button ${argsToTemplate(args)}>
      <svg lucideRefreshCw [size]="14" aria-hidden="true"></svg>
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

export const PauseResume: Story = {
  render: () => ({
    moduleMetadata: { imports: [MmIconButton, LucidePause, LucidePlay] },
    template: `<div style="display:flex;gap:12px">
      <mm-icon-button label="Pause Afterlight">
        <svg lucidePause [size]="14" aria-hidden="true"></svg>
      </mm-icon-button>
      <mm-icon-button label="Resume Afterlight">
        <svg lucidePlay [size]="14" aria-hidden="true"></svg>
      </mm-icon-button>
    </div>`,
  }),
  play: ({ canvasElement }) => {
    const buttons = canvasElement.querySelectorAll('button[aria-label]');
    if (buttons.length !== 2) throw new Error(`Expected 2 icon buttons, found ${buttons.length}`);
  },
};
