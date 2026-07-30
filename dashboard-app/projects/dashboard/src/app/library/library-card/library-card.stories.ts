import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { applicationConfig, type Meta, type StoryObj } from '@storybook/angular';
import { WatchNextItem } from '../watch-next.models';
import { WatchNextFacade, WatchNextStatus } from '../watch-next.facade';
import { LibraryCard } from './library-card';

const demoItems: WatchNextItem[] = [
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
];

function watchNextFacadeProvider(status: WatchNextStatus, error = '') {
  const items = status === 'empty' || status === 'error' ? [] : demoItems;
  return {
    provide: WatchNextFacade,
    useValue: {
      status: signal(status),
      items: signal(items),
      error: signal(error),
      refreshing: signal(false),
      lastFetchedAt: signal(''),
      movieCount: signal(items.filter((item) => item.kind === 'movie').length),
      seriesCount: signal(items.filter((item) => item.kind === 'episode').length),
      totalCount: signal(items.length),
      movies: signal(items.filter((item) => item.kind === 'movie')),
      series: signal(items.filter((item) => item.kind === 'episode')),
      refresh: () => Promise.resolve(),
    },
  };
}

const meta: Meta = {
  title: 'Dashboard/LibraryCard',
  component: LibraryCard,
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj;

export const Ready: Story = {
  decorators: [
    applicationConfig({
      providers: [provideRouter([]), watchNextFacadeProvider('ready')],
    }),
  ],
};

export const Loading: Story = {
  decorators: [
    applicationConfig({
      providers: [provideRouter([]), watchNextFacadeProvider('loading')],
    }),
  ],
};

export const ErrorState: Story = {
  decorators: [
    applicationConfig({
      providers: [
        provideRouter([]),
        watchNextFacadeProvider('error', 'Watch-next is temporarily unavailable.'),
      ],
    }),
  ],
};

export const Empty: Story = {
  decorators: [
    applicationConfig({
      providers: [provideRouter([]), watchNextFacadeProvider('empty')],
    }),
  ],
};
