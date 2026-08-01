import type { Meta, StoryObj } from '@storybook/angular';
import { MmInput } from './input';

const meta: Meta<MmInput> = { title: 'UI/Input', component: MmInput, tags: ['autodocs'] };
export default meta;
type Story = StoryObj<MmInput>;

export const Text: Story = {
  args: { kind: 'text', label: 'Title', placeholder: 'Enter a title' },
};

export const Textarea: Story = {
  args: { kind: 'textarea', label: 'Notes', placeholder: 'Optional notes' },
};

export const Error: Story = {
  args: {
    kind: 'text',
    label: 'Server URL',
    value: 'not-a-url',
    invalid: true,
    message: 'Enter a valid URL.',
  },
};

export const AriaLabelOnly: Story = {
  args: { kind: 'text', ariaLabel: 'Search current results', placeholder: 'Search current results' },
};
