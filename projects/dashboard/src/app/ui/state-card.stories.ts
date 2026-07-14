import type { Meta, StoryObj } from '@storybook/angular';
import { MmButton, MmStateCard } from './index';

const meta = {
  title: 'UI/StateCard',
  component: MmStateCard,
  tags: ['autodocs'],
  parameters: { a11y: { test: 'error' } },
} satisfies Meta<typeof MmStateCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const States: Story = {
  render: () => ({
    imports: [MmStateCard, MmButton],
    template: `<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;max-width:900px">
      <mm-state-card kind="loading" title="Loading" message="Fetching media" />
      <mm-state-card kind="empty" title="Empty" message="Nothing has been added" />
      <mm-state-card tone="danger" kind="error" title="Error" message="Try again">
        <mm-button label="Retry" />
      </mm-state-card>
    </div>`,
  }),
};
