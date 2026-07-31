import type { Meta, StoryObj } from '@storybook/angular';
import { MmLiveIndicator } from './live-indicator';

const meta: Meta<MmLiveIndicator> = {
  title: 'Primitives/LiveIndicator',
  component: MmLiveIndicator,
  tags: ['autodocs'],
  args: {
    label: 'Live',
    compact: false,
    reduced: false,
  },
};
export default meta;
type Story = StoryObj<MmLiveIndicator>;

export const Default: Story = {};

export const Compact: Story = {
  args: { compact: true },
};

export const Reduced: Story = {
  args: { reduced: true },
};

export const Ok: Story = {
  args: { tone: 'ok', label: 'Healthy' },
};

export const Warn: Story = {
  args: { tone: 'warn', label: 'Degraded' },
};

export const Down: Story = {
  args: { tone: 'down', label: 'Down' },
};

export const Gallery: Story = {
  render: () => ({
    template: `
      <div style="display:flex;align-items:center;gap:32px">
        <mm-live-indicator />
        <mm-live-indicator tone="ok" label="Healthy" />
        <mm-live-indicator tone="warn" label="Degraded" />
        <mm-live-indicator tone="down" label="Down" />
      </div>
    `,
    moduleMetadata: { imports: [MmLiveIndicator] },
  }),
};
