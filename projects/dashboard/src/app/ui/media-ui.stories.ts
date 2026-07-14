import type { Meta, StoryObj } from '@storybook/angular';
import { MmButton, MmPoster, MmProgress, MmStateCard, MmStatus } from './index';
import { MmThemePicker } from './index';

const meta = {
  title: 'media-ui/Gallery',
  component: MmButton,
  tags: ['autodocs'],
  parameters: { a11y: { test: 'error' } },
} satisfies Meta<typeof MmButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const CorePrimitives: Story = {
  render: () => ({
    imports: [MmButton, MmStatus, MmProgress, MmPoster, MmStateCard],
    template: `<main style="display:grid;gap:18px;max-width:680px">
      <section style="display:flex;gap:10px;align-items:center"><mm-button label="Continue" /><mm-button label="Cancel" variant="quiet" /><mm-button label="Loading" [busy]="true" /></section>
      <section style="display:flex;gap:10px;flex-wrap:wrap"><mm-status tone="success">Ready</mm-status><mm-status tone="warning">Needs review</mm-status><mm-status tone="danger">Failed</mm-status></section>
      <mm-progress [value]="68" label="Transcoding" />
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px"><mm-poster title="The Long Night" meta="2026 · 2h 08m" /><mm-poster title="Empty shelf" meta="No titles yet" art="linear-gradient(145deg, var(--mm-component-muted-bg), var(--mm-component-card-bg) 65%)" /><mm-poster title="Queued" meta="Queued · 24%" art="linear-gradient(145deg, var(--mm-component-warning), var(--mm-component-card-bg) 65%)" /></div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px"><mm-state-card kind="loading" title="Loading" message="Fetching media" /><mm-state-card kind="empty" title="Empty" message="Nothing has been added" /><mm-state-card tone="danger" kind="error" title="Error" message="Try again" /></div>
    </main>`,
  }),
};

export const ThemePicker: Story = {
  render: () => ({ imports: [MmThemePicker], template: '<mm-theme-picker />' }),
  play: async ({ canvasElement }) => {
    const select = canvasElement.querySelector<HTMLSelectElement>('select[aria-label="Choose theme"]');
    if (!select) throw new Error('Theme picker select was not rendered');
    select.value = 'tokyo-night';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    if (select.value !== 'tokyo-night') throw new Error('Theme selection did not update');
    if (document.documentElement.dataset['theme'] !== 'tokyo-night') {
      throw new Error('Theme was not applied to documentElement');
    }
    if (localStorage.getItem('media-ui-theme') !== 'tokyo-night') {
      throw new Error('Theme was not persisted to localStorage');
    }
  },
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
