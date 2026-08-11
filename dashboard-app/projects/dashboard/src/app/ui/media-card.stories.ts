import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MOCK_POSTER, mockArtUrl } from '../../testing/storybook-mock-art';
import { MmMediaCard } from './index';

type MediaCardArgs = {
  layout: 'portrait' | 'landscape';
  title: string;
  subtitle: string;
  rating: number | null;
  episode: string | null;
  tag: string | null;
  tagTone: 'accent' | 'success';
  progress: number | null;
  imageUrl: string | null;
  art: string;
  href: string | null;
  linkLabel: string | null;
  captionPlacement: 'overlay' | 'below' | 'none';
  showPlayCue: boolean;
};

const meta: Meta<MediaCardArgs> = {
  title: 'UI/MediaCard',
  component: MmMediaCard,
  tags: ['autodocs'],
  argTypes: {
    layout: { control: 'select', options: ['portrait', 'landscape'] },
    title: { control: 'text' },
    subtitle: { control: 'text' },
    rating: { control: { type: 'number', min: 0, max: 10, step: 0.1 } },
    episode: { control: 'text' },
    tag: { control: 'text' },
    tagTone: { control: 'select', options: ['accent', 'success'] },
    progress: { control: { type: 'number', min: 0, max: 100, step: 1 } },
    imageUrl: { control: 'text' },
    art: { control: 'text' },
    href: { control: 'text' },
    linkLabel: { control: 'text' },
    captionPlacement: { control: 'select', options: ['overlay', 'below', 'none'] },
    showPlayCue: { control: 'boolean' },
  },
  args: {
    layout: 'portrait',
    title: 'Neon Veil',
    subtitle: 'The Silent Witness',
    rating: null,
    episode: 'S1 · E6',
    tag: 'Continue',
    tagTone: 'accent',
    progress: 64,
    imageUrl: MOCK_POSTER.series1,
    art: mockArtUrl(MOCK_POSTER.series1),
    href: null,
    linkLabel: null,
    captionPlacement: 'overlay',
    showPlayCue: false,
  },
  render: (args) => ({
    props: args,
    template: `<div style="max-width:220px"><mm-media-card ${argsToTemplate(args)} /></div>`,
  }),
};

export default meta;
type Story = StoryObj<MediaCardArgs>;

export const Default: Story = {};

export const NewEpisode: Story = {
  args: {
    title: 'Mirror Shard',
    subtitle: 'Fracture',
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
    subtitle: 'No titles yet',
    rating: null,
    episode: null,
    tag: null,
    progress: null,
    imageUrl: null,
    art: 'linear-gradient(145deg, var(--mm-component-muted-bg), var(--mm-component-card-bg) 65%)',
  },
};

export const Linked: Story = {
  args: {
    title: 'Dune',
    subtitle: '2021 · Movie',
    rating: 8.0,
    episode: null,
    tag: '1',
    progress: null,
    imageUrl: MOCK_POSTER.movie1,
    art: mockArtUrl(MOCK_POSTER.movie1),
    href: 'https://trakt.tv/movies/dune-2021',
    linkLabel: 'Open Dune on Trakt',
  },
};

export const CaptionBelow: Story = {
  args: {
    title: 'Moonrise',
    subtitle: '2024 · Movie',
    episode: null,
    tag: null,
    progress: null,
    imageUrl: MOCK_POSTER.movie2,
    art: mockArtUrl(MOCK_POSTER.movie2),
    captionPlacement: 'below',
    href: 'https://jellyfin.example/web/index.html#!/details?id=m1',
    linkLabel: 'Play Moonrise',
    showPlayCue: true,
  },
};

export const Gallery: Story = {
  render: () => ({
    imports: [MmMediaCard],
    template: `<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;max-width:680px">
      <mm-media-card title="Neon Veil" subtitle="The Silent Witness" episode="S1 · E6" tag="Continue" [progress]="64" [imageUrl]="'${MOCK_POSTER.series1}'" />
      <mm-media-card title="The Apothecary's Garden" subtitle="Moonflower" episode="S1 · E8" tag="Continue" [progress]="82" [imageUrl]="'${MOCK_POSTER.movie1}'" />
      <mm-media-card title="Mirror Shard" subtitle="Fracture" episode="S1 · E1" tag="New" tagTone="success" [progress]="4" [imageUrl]="'${MOCK_POSTER.movie2}'" />
    </div>`,
  }),
};

export const Landscape: Story = {
  args: {
    layout: 'landscape',
    title: 'Moonrise',
    subtitle: 'Season 1 · Episode 6',
    rating: null,
    episode: null,
    tag: null,
    progress: null,
    imageUrl: null,
    art: mockArtUrl(MOCK_POSTER.series1),
    href: 'https://jellyfin.example/item',
    linkLabel: 'Continue Moonrise',
    captionPlacement: 'overlay',
    showPlayCue: true,
  },
  render: (args) => ({
    props: args,
    template: `<div style="max-width:480px"><mm-media-card ${argsToTemplate(args)} /></div>`,
  }),
};

export const LandscapeWithProgress: Story = {
  ...Landscape,
  args: {
    ...Landscape.args,
    progress: 42,
  },
};
