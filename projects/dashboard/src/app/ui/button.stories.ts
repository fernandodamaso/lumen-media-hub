import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MmButton } from './index';

type ButtonArgs = {
  label: string;
  variant: 'primary' | 'quiet' | 'success' | 'warning';
  disabled: boolean;
  busy: boolean;
  type: 'button' | 'submit';
};

const meta: Meta<ButtonArgs> = {
  title: 'UI/Button',
  component: MmButton,
  tags: ['autodocs'],
  argTypes: {
    label: { control: 'text' },
    variant: {
      control: 'select',
      options: ['primary', 'quiet', 'success', 'warning'],
    },
    disabled: { control: 'boolean' },
    busy: { control: 'boolean' },
    type: { control: 'select', options: ['button', 'submit'] },
  },
  args: {
    label: 'Continue',
    variant: 'primary',
    disabled: false,
    busy: false,
    type: 'button',
  },
  render: (args) => ({
    props: args,
    template: `<mm-button ${argsToTemplate(args)} />`,
  }),
};

export default meta;
type Story = StoryObj<ButtonArgs>;

export const Primary: Story = {};

export const Quiet: Story = {
  args: { label: 'Cancel', variant: 'quiet' },
};

export const Success: Story = {
  args: { label: 'Saved', variant: 'success' },
};

export const Warning: Story = {
  args: { label: 'Retry', variant: 'warning' },
};

export const Disabled: Story = {
  args: { label: 'Unavailable', disabled: true },
};

export const Loading: Story = {
  args: { label: 'Saving', busy: true },
};

export const KeyboardFocus: Story = {
  args: { label: 'Focus me' },
  play: async ({ canvasElement }) => {
    const button = canvasElement.querySelector<HTMLButtonElement>('button');
    if (!button) throw new Error('Button was not rendered');
    button.focus({ focusVisible: true });
    if (document.activeElement !== button) throw new Error('Button did not receive focus');
    const outline = getComputedStyle(button);
    if (outline.outlineStyle === 'none' || Number.parseFloat(outline.outlineWidth) <= 0) {
      throw new Error('Button focus ring is not visible');
    }
  },
};
