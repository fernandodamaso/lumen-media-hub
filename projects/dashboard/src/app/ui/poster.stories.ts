import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MmPoster } from './index';

type PosterArgs = {
  title: string;
  meta: string;
  rating: number | null;
  art: string;
};

const meta: Meta<PosterArgs> = {
  title: 'UI/Poster',
  component: MmPoster,
  tags: ['autodocs'],
  argTypes: {
    title: { control: 'text' },
    meta: { control: 'text' },
    rating: { control: { type: 'number', min: 0, max: 10, step: 0.1 } },
    art: { control: 'text' },
  },
  args: {
    title: 'The Long Night',
    meta: '2026 · 2h 08m',
    rating: 8.4,
    art: 'linear-gradient(145deg, color-mix(in srgb, var(--mm-component-accent) 28%, var(--mm-component-card-bg)), var(--mm-component-card-bg) 72%)',
  },
  render: (args) => ({
    props: args,
    template: `<div style="max-width:220px"><mm-poster ${argsToTemplate(args)} /></div>`,
  }),
};

export default meta;
type Story = StoryObj<PosterArgs>;

export const Default: Story = {};

export const WithoutRating: Story = {
  args: {
    title: 'Empty shelf',
    meta: 'No titles yet',
    rating: null,
    art: 'linear-gradient(145deg, var(--mm-component-muted-bg), var(--mm-component-card-bg) 65%)',
  },
};

export const Queued: Story = {
  args: {
    title: 'Queued',
    meta: 'Queued · 24%',
    rating: null,
    art: 'linear-gradient(145deg, var(--mm-component-warning), var(--mm-component-card-bg) 65%)',
  },
};

export const Gallery: Story = {
  render: () => ({
    imports: [MmPoster],
    template: `<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;max-width:680px">
      <mm-poster title="The Long Night" meta="2026 · 2h 08m" [rating]="8.4" />
      <mm-poster title="Empty shelf" meta="No titles yet" art="linear-gradient(145deg, var(--mm-component-muted-bg), var(--mm-component-card-bg) 65%)" />
      <mm-poster title="Queued" meta="Queued · 24%" art="linear-gradient(145deg, var(--mm-component-warning), var(--mm-component-card-bg) 65%)" />
    </div>`,
  }),
  play: async ({ canvasElement }) => {
    const posters = canvasElement.querySelectorAll('.mm-poster');
    if (posters.length !== 3) throw new Error(`Expected 3 posters, found ${posters.length}`);
    const titles = [...canvasElement.querySelectorAll('.mm-poster strong')].map((el) => el.textContent?.trim());
    if (!titles.includes('The Long Night') || !titles.includes('Empty shelf') || !titles.includes('Queued')) {
      throw new Error(`Poster titles missing: ${titles.join(', ')}`);
    }
    const rating = canvasElement.querySelector('.mm-poster__rating');
    if (!rating?.textContent?.includes('8.4')) {
      throw new Error('Rated poster is missing its rating badge');
    }
  },
};
