import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { WatchNextGrid } from './watch-next-grid';
import { WatchNextItem } from '../watch-next.models';

type WatchNextGridArgs = {
  items: WatchNextItem[];
  compact: boolean;
};

const sampleItems: WatchNextItem[] = [
  {
    id: 'ep-1',
    parentId: 'series-1',
    title: 'The Expanse',
    subtitle: 'S04E02 · Jetsam',
    kind: 'episode',
    art: 'linear-gradient(145deg, #1e3a5f, #0b1220 70%)',
    artworkState: 'ok',
    href: null,
    playable: true,
    progressPercent: 42,
    year: null,
    rating: null,
    genres: [],
    overview: null,
    runtimeTicks: null,
    positionTicks: null,
    backdropUrl: null,
    thumbUrl: null,
  },
  {
    id: 'mv-1',
    parentId: null,
    title: 'Dune',
    subtitle: '',
    kind: 'movie',
    art: 'linear-gradient(145deg, #8b5a2b, #1a1410 70%)',
    artworkState: 'ok',
    href: null,
    playable: true,
    progressPercent: 18,
    year: null,
    rating: null,
    genres: [],
    overview: null,
    runtimeTicks: null,
    positionTicks: null,
    backdropUrl: null,
    thumbUrl: null,
  },
  {
    id: 'mv-2',
    parentId: null,
    title: 'Night Transit',
    subtitle: '',
    kind: 'movie',
    art: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
    artworkState: 'missing',
    href: null,
    playable: true,
    progressPercent: 0,
    year: null,
    rating: null,
    genres: [],
    overview: null,
    runtimeTicks: null,
    positionTicks: null,
    backdropUrl: null,
    thumbUrl: null,
  },
];

const meta: Meta<WatchNextGridArgs> = {
  title: 'Dashboard/WatchNextGrid',
  component: WatchNextGrid,
  tags: ['autodocs'],
  args: {
    items: sampleItems,
    compact: true,
  },
  render: (args) => ({
    props: args,
    template: `<div style="max-width:960px"><mm-watch-next-grid ${argsToTemplate(args)} /></div>`,
  }),
};

export default meta;
type Story = StoryObj<WatchNextGridArgs>;

export const Ready: Story = {};

export const MissingArtwork: Story = {
  args: {
    items: [sampleItems[2]],
  },
};

export const Empty: Story = {
  args: {
    items: [],
  },
};

const unwatchedEpisode: WatchNextItem = {
  id: 'ep-next',
  parentId: 'series-2',
  title: 'The Blue Hour',
  subtitle: 'S02E03 · Nightfall',
  kind: 'episode',
  art: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
  artworkState: 'ok',
  href: null,
  playable: true,
  progressPercent: 0,
  year: null,
  rating: null,
  genres: [],
  overview: null,
  runtimeTicks: null,
  positionTicks: null,
  backdropUrl: null,
  thumbUrl: null,
};

export const UnwatchedEpisode: Story = {
  args: {
    items: [unwatchedEpisode],
  },
};
