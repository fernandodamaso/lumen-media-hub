import { type Meta, type StoryObj } from '@storybook/angular';
import { DashboardHeader } from './dashboard-header';

type HeaderArgs = {
  syncedAt: string;
};

const meta: Meta<HeaderArgs> = {
  title: 'Dashboard/Header',
  component: DashboardHeader,
  tags: ['autodocs'],
  argTypes: {
    syncedAt: { control: 'text' },
  },
  args: {
    syncedAt: '2 minutes ago',
  },
};

export default meta;
type Story = StoryObj<HeaderArgs>;

export const Default: Story = {};

export const JustSynced: Story = {
  args: { syncedAt: 'just now' },
};

export const SyncUnavailable: Story = {
  args: { syncedAt: '' },
};
