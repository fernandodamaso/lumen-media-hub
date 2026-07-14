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
  play: async ({ canvasElement }) => {
    const cards = canvasElement.querySelectorAll('.mm-state-card');
    if (cards.length !== 3) throw new Error(`Expected 3 state cards, found ${cards.length}`);
    if (!canvasElement.querySelector('.mm-state-card--danger')) {
      throw new Error('Error state card is missing its danger tone');
    }
    const retry = [...canvasElement.querySelectorAll('button')].find((button) => button.textContent?.trim() === 'Retry');
    if (!retry) throw new Error('Retry action was not rendered on the error state card');
    retry.focus({ focusVisible: true });
    if (document.activeElement !== retry) throw new Error('Retry action did not receive focus');
    const outline = getComputedStyle(retry);
    if (outline.outlineStyle === 'none' || Number.parseFloat(outline.outlineWidth) <= 0) {
      throw new Error('Retry action focus ring is not visible');
    }
  },
};
