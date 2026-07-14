import type { Meta, StoryObj } from '@storybook/angular';
import { MmPoster } from './index';

const meta = {
  title: 'UI/Poster',
  component: MmPoster,
  tags: ['autodocs'],
  parameters: { a11y: { test: 'error' } },
} satisfies Meta<typeof MmPoster>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Gallery: Story = {
  render: () => ({
    imports: [MmPoster],
    template: `<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;max-width:680px">
      <mm-poster title="The Long Night" meta="2026 · 2h 08m" [rating]="8.4" />
      <mm-poster title="Empty shelf" meta="No titles yet" art="linear-gradient(145deg, var(--mm-component-muted-bg), var(--mm-component-card-bg) 65%)" />
      <mm-poster title="Queued" meta="Queued · 24%" art="linear-gradient(145deg, var(--mm-component-warning), var(--mm-component-card-bg) 65%)" />
    </div>`,
  }),
};
