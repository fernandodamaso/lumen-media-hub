import type { Meta, StoryObj } from '@storybook/angular';
import { MmButton, MmCard } from './index';

const meta = {
  title: 'UI/Card',
  component: MmCard,
  tags: ['autodocs'],
  parameters: { a11y: { test: 'error' } },
} satisfies Meta<typeof MmCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => ({
    imports: [MmCard, MmButton],
    template: `<div style="max-width:420px;height:280px">
      <mm-card labelledBy="card-heading">
        <h2 mm-card-header id="card-heading">Downloads</h2>
        <mm-button mm-card-header-actions label="Refresh" variant="quiet" />
        <p>Active transfers and queue health for the current Demo session.</p>
        <span mm-card-footer>Updated just now</span>
        <mm-button mm-card-footer-actions label="Open" variant="quiet" />
      </mm-card>
    </div>`,
  }),
};

export const BodyOnly: Story = {
  render: () => ({
    imports: [MmCard],
    template: `<div style="max-width:420px">
      <mm-card>
        <p>A minimal card with content only — header and footer stay hidden when empty.</p>
      </mm-card>
    </div>`,
  }),
};
