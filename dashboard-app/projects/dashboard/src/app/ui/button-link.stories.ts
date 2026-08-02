import type { Meta, StoryObj } from '@storybook/angular';
import { MmButtonLink } from './button-link';

const meta: Meta<MmButtonLink> = {
  title: 'UI/ButtonLink',
  component: MmButtonLink,
  tags: ['autodocs'],
  args: { destination: '/library', label: 'Open library', variant: 'primary', size: 'md', mode: 'internal' },
};

export default meta;
type Story = StoryObj<MmButtonLink>;
export const Internal: Story = {
  play: ({ canvasElement }) => {
    const link = canvasElement.querySelector<HTMLAnchorElement>('a');
    link?.focus();
    if (document.activeElement !== link) throw new Error('ButtonLink should receive keyboard focus');
  },
};
export const External: Story = { args: { destination: 'https://example.com', mode: 'external', icon: 'external-link' } };
