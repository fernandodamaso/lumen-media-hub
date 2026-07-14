import { TestBed } from '@angular/core/testing';
import {
  JELLYFIN_LINK_BASES,
  MEDIA_STACK_API,
  MediaStackApi,
  MediaStackLibraryItemDto,
  MediaStackTorrentDto,
} from '../media-stack/media-stack-api';
import { LibraryFacade } from './library.facade';

describe('LibraryFacade', () => {
  let api: MockApi;
  let facade: LibraryFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [
        LibraryFacade,
        { provide: MEDIA_STACK_API, useValue: api },
        { provide: JELLYFIN_LINK_BASES, useValue: { jellyfinBase: 'https://jellyfin.example/' } },
      ],
    });
    facade = TestBed.inject(LibraryFacade);
  });

  it('defaults to movies and exposes matching items with counts', async () => {
    await facade.refresh();
    expect(facade.kind()).toBe('movie');
    expect(facade.status()).toBe('ready');
    expect(facade.movieCount()).toBe(2);
    expect(facade.seriesCount()).toBe(2);
    expect(facade.items().every((item) => item.kind === 'movie')).toBe(true);
    expect(facade.items()[0].href).toBe('https://jellyfin.example/web/index.html#!/details?id=jf-dune');
  });

  it('switches collection and keeps inactive tab counts accurate', async () => {
    await facade.refresh();
    facade.setKind('series');
    expect(facade.kind()).toBe('series');
    expect(facade.items().map((item) => item.title)).toEqual(['Cowboy Bebop', 'Broken Signal']);
    expect(facade.movieCount()).toBe(2);
    expect(facade.seriesCount()).toBe(2);
  });

  it('exposes empty and error states', async () => {
    api.items = [];
    await facade.refresh();
    expect(facade.status()).toBe('empty');
    expect(facade.movieCount()).toBe(0);

    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');
  });

  it('keeps empty status for the active kind when the other collection has items', async () => {
    api.items = [
      {
        id: 'jf-cowboy',
        title: 'Cowboy Bebop',
        kind: 'series',
        year: 1998,
        posterUrl: 'linear-gradient(145deg, #b45309, #1c1917 70%)',
      },
    ];
    await facade.refresh();
    expect(facade.kind()).toBe('movie');
    expect(facade.status()).toBe('empty');
    expect(facade.movieCount()).toBe(0);
    expect(facade.seriesCount()).toBe(1);
  });

  it('ignores unsupported library kinds when building the catalog', async () => {
    api.items = [
      {
        id: 'jf-dune',
        title: 'Dune',
        kind: 'movie',
        year: 2021,
        posterUrl: 'linear-gradient(145deg, #8b5a2b, #1a1410 70%)',
      },
      {
        id: 'jf-season',
        title: 'Season 1',
        kind: 'Season',
      },
      {
        id: 'jf-cowboy',
        title: 'Cowboy Bebop',
        kind: 'series',
        year: 1998,
        posterUrl: 'linear-gradient(145deg, #b45309, #1c1917 70%)',
      },
    ];
    await facade.refresh();
    expect(facade.movieCount()).toBe(1);
    expect(facade.seriesCount()).toBe(1);
    expect(facade.items().map((item) => item.id)).toEqual(['jf-dune']);
  });

  it('keeps loading status when kind changes mid-refresh', async () => {
    let resolveLoad!: (value: MediaStackLibraryItemDto[]) => void;
    api.listLibraryItems = () =>
      new Promise((resolve) => {
        resolveLoad = resolve;
      });

    const pending = facade.refresh();
    expect(facade.status()).toBe('loading');
    facade.setKind('series');
    expect(facade.status()).toBe('loading');

    resolveLoad(api.items.map((item) => ({ ...item })));
    await pending;
    expect(facade.kind()).toBe('series');
    expect(facade.status()).toBe('ready');
    expect(facade.items().every((item) => item.kind === 'series')).toBe(true);
  });

  it('returns null href when jellyfin base is missing', async () => {
    TestBed.resetTestingModule();
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [
        LibraryFacade,
        { provide: MEDIA_STACK_API, useValue: api },
        { provide: JELLYFIN_LINK_BASES, useValue: { jellyfinBase: '' } },
      ],
    });
    facade = TestBed.inject(LibraryFacade);
    await facade.refresh();
    expect(facade.items().every((item) => item.href === null)).toBe(true);
  });
});

class MockApi implements MediaStackApi {
  items: MediaStackLibraryItemDto[] = [
    {
      id: 'jf-dune',
      title: 'Dune',
      kind: 'movie',
      year: 2021,
      posterUrl: 'linear-gradient(145deg, #8b5a2b, #1a1410 70%)',
    },
    {
      id: 'jf-night',
      title: 'Night Transit',
      kind: 'movie',
      year: 2026,
      artworkState: 'missing',
    },
    {
      id: 'jf-cowboy',
      title: 'Cowboy Bebop',
      kind: 'series',
      year: 1998,
      posterUrl: 'linear-gradient(145deg, #b45309, #1c1917 70%)',
    },
    {
      id: 'jf-broken',
      title: 'Broken Signal',
      kind: 'series',
      artworkState: 'failed',
      posterUrl: 'http://example.invalid/x.jpg',
    },
  ];
  failure = false;

  listTorrents(): Promise<MediaStackTorrentDto[]> {
    return Promise.resolve([]);
  }
  pauseAll(): Promise<void> {
    return Promise.resolve();
  }
  resumeAll(): Promise<void> {
    return Promise.resolve();
  }
  listCalendarEvents() {
    return Promise.resolve([]);
  }
  getArrLibrary() {
    return Promise.resolve({ ok: true, series: {}, movies: {} });
  }
  listLibraryItems() {
    return this.failure
      ? Promise.reject(new Error('offline'))
      : Promise.resolve(this.items.map((item) => ({ ...item })));
  }
  getAutomationSummary() {
    return Promise.resolve({ generatedAt: '', services: [], preview: [], problems: [] });
  }
  listHermesRecommendations() {
    return Promise.resolve({ ok: true, items: [] });
  }
  submitHermesFeedback() {
    return Promise.resolve({ ok: true });
  }
  requestHermesMore() {
    return Promise.resolve({ ok: true });
  }
  listJellyseerrDiscover() {
    return Promise.resolve({ ok: true, items: [] });
  }
  listTraktDiscover() {
    return Promise.resolve({ ok: true, items: [] });
  }
  requestMedia() {
    return Promise.resolve({ ok: true });
  }
  listCronLogs() {
    return Promise.resolve({ ok: true, logs: [] });
  }
}
