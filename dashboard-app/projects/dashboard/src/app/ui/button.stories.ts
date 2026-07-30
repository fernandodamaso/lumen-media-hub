import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MmButton } from './index';

type ButtonArgs = {
  label: string;
  variant: 'primary' | 'quiet' | 'success' | 'warning' | 'danger' | 'gold' | 'ghost';
  size: 'sm' | 'md' | 'lg';
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
      options: ['primary', 'quiet', 'success', 'warning', 'danger', 'gold', 'ghost'],
    },
    disabled: { control: 'boolean' },
    busy: { control: 'boolean' },
    size: { control: 'select', options: ['sm', 'md', 'lg'] },
    type: { control: 'select', options: ['button', 'submit'] },
  },
  args: {
    label: 'Continue',
    variant: 'primary',
    size: 'md',
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

export const Gold: Story = {
  args: { label: 'Add media', variant: 'gold' },
};

export const Ghost: Story = {
  args: { label: 'Details', variant: 'ghost' },
};

export const Quiet: Story = {
  args: { label: 'Cancel', variant: 'quiet' },
};

export const Success: Story = {
  args: { label: 'Saved', variant: 'success' },
};

export const Warning: Story = {
  args: { label: 'Retry', variant: 'warning' },
};

export const Danger: Story = {
  args: { label: 'View issues', variant: 'danger' },
};

export const AllVariants: Story = {
  render: () => ({
    template: `
      <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center">
        <mm-button label="Continue" variant="primary" />
        <mm-button label="Add media" variant="gold" />
        <mm-button label="Details" variant="ghost" />
        <mm-button label="Cancel" variant="quiet" />
        <mm-button label="Saved" variant="success" />
        <mm-button label="Retry" variant="warning" />
        <mm-button label="View issues" variant="danger" />
      </div>
    `,
  }),
};

export const Disabled: Story = {
  args: { label: 'Unavailable', disabled: true },
};

export const Loading: Story = {
  args: { label: 'Saving', busy: true },
};

export const Small: Story = {
  args: { label: 'Resume all', variant: 'quiet', size: 'sm' },
};

export const Large: Story = {
  args: { label: 'Play', variant: 'gold', size: 'lg' },
};

export const ChipLike: Story = {
  args: { label: 'Resume all', variant: 'gold', size: 'sm' },
};

export const KeyboardFocus: Story = {
  args: { label: 'Focus me' },
  play: ({ canvasElement }) => {
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
