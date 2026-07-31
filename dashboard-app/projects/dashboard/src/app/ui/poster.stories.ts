import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MOCK_POSTER, mockArtUrl } from '../../testing/storybook-mock-art';
import { MmPoster } from './index';

type PosterArgs = {
  title: string;
  meta: string;
  rating: number | null;
  episode: string | null;
  tag: string | null;
  tagTone: 'accent' | 'success';
  progress: number | null;
  imageUrl: string | null;
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
    episode: { control: 'text' },
    tag: { control: 'text' },
    tagTone: { control: 'select', options: ['accent', 'success'] },
    progress: { control: { type: 'number', min: 0, max: 100, step: 1 } },
    imageUrl: { control: 'text' },
    art: { control: 'text' },
  },
  args: {
    title: 'Neon Veil',
    meta: 'The Silent Witness',
    rating: null,
    episode: 'S1 · E6',
    tag: 'Continue',
    tagTone: 'accent',
    progress: 64,
    imageUrl: MOCK_POSTER.series1,
    art: mockArtUrl(MOCK_POSTER.series1),
  },
  render: (args) => ({
    props: args,
    template: `<div style="max-width:220px"><mm-poster ${argsToTemplate(args)} /></div>`,
  }),
};

export default meta;
type Story = StoryObj<PosterArgs>;

export const Default: Story = {};

export const NewEpisode: Story = {
  args: {
    title: 'Mirror Shard',
    meta: 'Fracture',
    episode: 'S1 · E1',
    tag: 'New',
    tagTone: 'success',
    progress: 4,
    imageUrl: MOCK_POSTER.movie2,
    art: mockArtUrl(MOCK_POSTER.movie2),
  },
};

export const WithoutRating: Story = {
  args: {
    title: 'Empty shelf',
    meta: 'No titles yet',
    rating: null,
    episode: null,
    tag: null,
    progress: null,
    imageUrl: null,
    art: 'linear-gradient(145deg, var(--mm-component-muted-bg), var(--mm-component-card-bg) 65%)',
  },
};

export const Gallery: Story = {
  render: () => ({
    imports: [MmPoster],
    template: `<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;max-width:680px">
      <mm-poster title="Neon Veil" meta="The Silent Witness" episode="S1 · E6" tag="Continue" [progress]="64" [imageUrl]="'${MOCK_POSTER.series1}'" />
      <mm-poster title="The Apothecary's Garden" meta="Moonflower" episode="S1 · E8" tag="Continue" [progress]="82" [imageUrl]="'${MOCK_POSTER.movie1}'" />
      <mm-poster title="Mirror Shard" meta="Fracture" episode="S1 · E1" tag="New" tagTone="success" [progress]="4" [imageUrl]="'${MOCK_POSTER.movie2}'" />
    </div>`,
  }),
};
