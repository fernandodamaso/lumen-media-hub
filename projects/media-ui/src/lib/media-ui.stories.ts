import type { Meta, StoryObj } from '@storybook/angular';
import { MmButton, MmPoster, MmProgress, MmStateCard, MmStatus } from '../public-api';
import { MmThemePicker } from '../public-api';

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
      <section style="display:flex;gap:10px;align-items:center"><mm-button>Continue</mm-button><mm-button variant="quiet">Cancel</mm-button><mm-button [busy]="true">Loading</mm-button></section>
      <section style="display:flex;gap:10px;flex-wrap:wrap"><mm-status tone="success">Ready</mm-status><mm-status tone="warning">Needs review</mm-status><mm-status tone="danger">Failed</mm-status></section>
      <mm-progress [value]="68" label="Transcoding" />
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px"><mm-poster title="The Long Night" meta="2026 · 2h 08m" /><mm-poster title="Empty shelf" [muted]="true" /><mm-poster title="Queued" [progress]="24" /></div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px"><mm-state-card icon="◌" title="Loading" message="Fetching media" /><mm-state-card icon="□" title="Empty" message="Nothing has been added" /><mm-state-card tone="danger" icon="!" title="Error" message="Try again" /></div>
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
  },
};

export const KeyboardFocus: Story = {
  render: () => ({ imports: [MmButton], template: '<mm-button>Focus me</mm-button>' }),
  play: async ({ canvasElement }) => {
    const button = canvasElement.querySelector<HTMLButtonElement>('button');
    if (!button) throw new Error('Button was not rendered');
    button.focus();
    if (document.activeElement !== button) throw new Error('Button did not receive focus');
  },
};
