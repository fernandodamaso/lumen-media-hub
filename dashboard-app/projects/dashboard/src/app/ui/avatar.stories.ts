import type { Meta, StoryObj } from '@storybook/angular';
import { MmAvatar, MmAvatarStack } from './avatar';

const meta: Meta<MmAvatar> = {
  title: 'Primitives/Avatar',
  component: MmAvatar,
  tags: ['autodocs'],
};
export default meta;
type Story = StoryObj<MmAvatar>;

export const Default: Story = { args: { initials: 'M', label: 'Media' } };
export const Gold: Story = { args: { initials: 'G', tone: 'gold' } };

export const Stack: Story = {
  render: () => ({
    template: `
      <mm-avatar-stack>
        <mm-avatar initials="A" tone="gold" />
        <mm-avatar initials="B" tone="violet" />
        <mm-avatar initials="C" tone="green" />
      </mm-avatar-stack>
    `,
    moduleMetadata: { imports: [MmAvatar, MmAvatarStack] },
  }),
};
