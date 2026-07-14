import type { Meta, StoryObj } from '@storybook/angular';
import { MmButton } from './index';

const meta = {
  title: 'UI/Button',
  component: MmButton,
  tags: ['autodocs'],
  parameters: { a11y: { test: 'error' } },
} satisfies Meta<typeof MmButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  render: () => ({ imports: [MmButton], template: '<mm-button label="Continue" />' }),
};

export const Variants: Story = {
  render: () => ({
    imports: [MmButton],
    template: `<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <mm-button label="Continue" />
      <mm-button label="Cancel" variant="quiet" />
      <mm-button label="Success" variant="success" />
      <mm-button label="Warning" variant="warning" />
      <mm-button label="Loading" [busy]="true" />
    </div>`,
  }),
};

export const KeyboardFocus: Story = {
  render: () => ({ imports: [MmButton], template: '<mm-button label="Focus me" />' }),
  play: async ({ canvasElement }) => {
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
