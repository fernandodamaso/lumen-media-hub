import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MmButton } from './index';

type ButtonArgs = {
  label: string;
  variant: 'primary' | 'quiet' | 'success' | 'warning' | 'danger' | 'gold' | 'ghost' | 'chip';
  size: 'sm' | 'md' | 'lg';
  disabled: boolean;
  busy: boolean;
  type: 'button' | 'submit';
  solid: boolean;
  icon: 'pause' | 'play' | 'plus' | 'refresh' | 'external-link' | '';
};

const meta: Meta<ButtonArgs> = {
  title: 'UI/Button',
  component: MmButton,
  tags: ['autodocs'],
  argTypes: {
    label: { control: 'text' },
    variant: {
      control: 'select',
      options: ['primary', 'quiet', 'success', 'warning', 'danger', 'gold', 'ghost', 'chip'],
    },
    disabled: { control: 'boolean' },
    busy: { control: 'boolean' },
    solid: { control: 'boolean' },
    icon: { control: 'select', options: ['', 'pause', 'play', 'plus', 'refresh', 'external-link'] },
    size: { control: 'select', options: ['sm', 'md', 'lg'] },
    type: { control: 'select', options: ['button', 'submit'] },
  },
  args: {
    label: 'Continue',
    variant: 'primary',
    size: 'md',
    disabled: false,
    busy: false,
    solid: false,
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
      <div style="display:flex;flex-direction:column;gap:16px;align-items:flex-start">
        <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center">
          <mm-button label="Continue" variant="primary" />
          <mm-button label="Add media" variant="gold" />
          <mm-button label="Details" variant="ghost" />
          <mm-button label="Cancel" variant="quiet" />
          <mm-button label="Saved" variant="success" />
          <mm-button label="Retry" variant="warning" />
          <mm-button label="View issues" variant="danger" />
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center">
          <mm-button label="Filter" variant="chip" />
          <mm-button label="Active" variant="chip" [solid]="true" />
        </div>
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

export const Chip: Story = {
  args: { label: 'Filter', variant: 'chip' },
};

export const ChipSolid: Story = {
  args: { label: 'Active', variant: 'chip', solid: true },
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

export const WithIcon: Story = {
  args: { label: 'Add media', variant: 'gold', icon: 'plus' },
};

export const IconGallery: Story = {
  render: () => ({
    template: `
      <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center">
        <mm-button label="Add media" variant="gold" icon="plus" />
        <mm-button label="Play" variant="primary" icon="play" />
        <mm-button label="Pause" variant="quiet" icon="pause" />
        <mm-button label="Refresh" variant="ghost" icon="refresh" />
        <mm-button label="Open in Jellyfin" variant="chip" icon="external-link" />
      </div>
    `,
    moduleMetadata: { imports: [MmButton] },
  }),
};
