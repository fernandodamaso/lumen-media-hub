import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { ServiceHealthFacade } from '../../automation/service-health.facade';
import { AutomationFacade } from '../../automation/automation.facade';
import { CalendarFacade } from '../../calendar/calendar.facade';
import { DownloadsAction, DownloadsFacade, DownloadsStatus } from '../../downloads/downloads.facade';
import { DownloadTorrent } from '../../downloads/downloads.models';
import { LibraryStatsFacade, LibraryStatsStatus } from '../../library/library-stats.facade';
import { LibraryItemsFacade, LibraryItemsStatus } from '../../library/library-items.facade';
import { WatchNextFacade, WatchNextStatus } from '../../library/watch-next.facade';
import { WatchNextItem } from '../../library/watch-next.models';
import { JELLYFIN_LINK_BASES, LibraryItem, LibraryStats } from '../../library/library.models';
import { StorageFacade } from '../../storage/storage.facade';
import { StorageOverview } from '../../storage/storage.models';
import { ActivityFacade } from '../../right-rail/activity.facade';
import { TrendingFacade, TrendingItem, TrendingStatus } from '../trending.facade';
import { HeroFacade } from '../dashboard-hero/hero.facade';
import { fixtureHost } from '../../../testing/fixture-host';
import { DashboardPage } from './dashboard-page';

function watchNextItem(overrides: Partial<WatchNextItem> = {}): WatchNextItem {
  return {
    id: 'e1',
    parentId: 's1',
    title: 'Night Watch',
    subtitle: 'S01E01 · Pilot',
    kind: 'episode',
    art: 'linear-gradient(#000, #111)',
    artworkState: 'ok',
    href: 'http://jf/web/index.html#!/details?id=e1',
    playable: true,
    progressPercent: 64,
    year: 2026,
    rating: 8.1,
    genres: ['Drama'],
    overview: '',
    runtimeTicks: null,
    positionTicks: null,
    backdropUrl: null,
    thumbUrl: 'http://jf/Items/e1/Images/Thumb',
    ...overrides,
  };
}

function libraryItem(overrides: Partial<LibraryItem> = {}): LibraryItem {
  return {
    id: 'lib-1',
    title: 'After Us',
    kind: 'series',
    meta: '2026 · Series',
    art: 'linear-gradient(#111, #222)',
    overview: '',
    href: null,
    artworkState: 'ok',
    playable: true,
    ...overrides,
  };
}

function trendingItem(overrides: Partial<TrendingItem> = {}): TrendingItem {
  return {
    id: 'trakt-tv-1',
    title: 'Wasteland',
    year: 2026,
    type: 'tv',
    posterUrl: null,
    rating: null,
    rank: 1,
    ...overrides,
  };
}

function torrent(): DownloadTorrent {
  return {
    id: 'a',
    name: 'Signal Drift',
    state: 'downloading',
    progress: 50,
    size: 100,
    downloaded: 50,
    downloadRate: 10,
    uploadRate: 2,
    eta: 30,
    category: 'Movies',
  };
}

describe('DashboardPage composition', () => {
  let fixture: ComponentFixture<DashboardPage>;
  let watchNext: {
    status: ReturnType<typeof signal<WatchNextStatus>>;
    items: ReturnType<typeof signal<WatchNextItem[]>>;
    totalCount: ReturnType<typeof signal<number>>;
    error: ReturnType<typeof signal<string>>;
    refresh: ReturnType<typeof vi.fn>;
  };
  let libraryItems: {
    status: ReturnType<typeof signal<LibraryItemsStatus>>;
    items: ReturnType<typeof signal<LibraryItem[]>>;
    error: ReturnType<typeof signal<string>>;
    refresh: ReturnType<typeof vi.fn>;
  };
  let libraryStats: {
    status: ReturnType<typeof signal<LibraryStatsStatus>>;
    stats: ReturnType<typeof signal<LibraryStats | null>>;
    error: ReturnType<typeof signal<string>>;
    refresh: ReturnType<typeof vi.fn>;
  };
  let trending: {
    status: ReturnType<typeof signal<TrendingStatus>>;
    items: ReturnType<typeof signal<TrendingItem[]>>;
    error: ReturnType<typeof signal<string>>;
    refresh: ReturnType<typeof vi.fn>;
  };
  let downloads: Record<string, unknown>;
  let storage: Record<string, unknown>;
  let calendar: Record<string, unknown>;
  let automation: Record<string, unknown>;
  let activity: Record<string, unknown>;
  let health: Record<string, unknown>;

  beforeEach(() => {
    watchNext = {
      status: signal<WatchNextStatus>('ready'),
      items: signal<WatchNextItem[]>([watchNextItem()]),
      totalCount: signal(1),
      error: signal(''),
      refresh: vi.fn(),
    };
    libraryItems = {
      status: signal<LibraryItemsStatus>('ready'),
      items: signal<LibraryItem[]>([libraryItem()]),
      error: signal(''),
      refresh: vi.fn(),
    };
    libraryStats = {
      status: signal<LibraryStatsStatus>('ready'),
      stats: signal<LibraryStats | null>({ movies: 428, series: 76, availability: 'complete' }),
      error: signal(''),
      refresh: vi.fn(),
    };
    trending = {
      status: signal<TrendingStatus>('ready'),
      items: signal<TrendingItem[]>([trendingItem(), trendingItem({ id: 'trakt-movie-2', title: 'Frontline', type: 'movie', rank: 2 })]),
      error: signal(''),
      refresh: vi.fn(),
    };
    downloads = {
      status: signal<DownloadsStatus>('ready'),
      torrents: signal<DownloadTorrent[]>([torrent()]),
      error: signal(''),
      notice: signal(''),
      pendingAction: signal<DownloadsAction | null>(null),
      pendingTorrentId: signal<string | null>(null),
      summary: signal({ active: 1, total: 1, downloaded: 50, size: 100, downloadRate: 10, uploadRate: 2 }),
      canPauseAll: signal(true),
      canResumeAll: signal(false),
      startPolling: vi.fn(),
      stopPolling: vi.fn(),
      refresh: vi.fn(),
      runAction: vi.fn(),
      runTorrentAction: vi.fn(),
    };
    storage = {
      status: signal('ready'),
      overview: signal<StorageOverview | null>({
        generatedAt: '',
        volumes: [{ id: 'media', label: 'Media library', kind: 'library', usedBytes: 5 * 1024 ** 3, totalBytes: 10 * 1024 ** 3 }],
      }),
      volumes: signal([{ id: 'media', label: 'Media library', kind: 'library', usedBytes: 5 * 1024 ** 3, totalBytes: 10 * 1024 ** 3 }]),
      refresh: vi.fn(),
    };
    calendar = { status: signal('ready'), refresh: vi.fn() };
    automation = { status: signal('ready'), refresh: vi.fn() };
    activity = { status: signal('ready'), refresh: vi.fn() };
    health = {
      status: signal('ready'),
      services: signal([{ id: 'jellyfin', name: 'Jellyfin', status: 'healthy', detail: '', latencyMs: 10 }]),
      health: signal({ overall: 'healthy' as const, actionableCount: 0 }),
      refresh: vi.fn(),
    };

    TestBed.configureTestingModule({
      imports: [DashboardPage],
      providers: [
        provideRouter([]),
        { provide: ServiceHealthFacade, useValue: health },
        { provide: LibraryStatsFacade, useValue: libraryStats },
        { provide: LibraryItemsFacade, useValue: libraryItems },
        { provide: WatchNextFacade, useValue: watchNext },
        { provide: TrendingFacade, useValue: trending },
        { provide: DownloadsFacade, useValue: downloads },
        { provide: StorageFacade, useValue: storage },
        { provide: CalendarFacade, useValue: calendar },
        { provide: AutomationFacade, useValue: automation },
        { provide: ActivityFacade, useValue: activity },
        { provide: JELLYFIN_LINK_BASES, useValue: { jellyfinBase: 'http://jf.local' } },
        { provide: HeroFacade, useValue: { view: signal(null) } },
      ],
    });
    fixture = TestBed.createComponent(DashboardPage);
  });

  it('renders the hero above the stat strip when a candidate qualifies', () => {
    fixture.detectChanges();
    const hero = fixtureHost(fixture).querySelector('mm-dashboard-hero');
    const strip = fixtureHost(fixture).querySelector('mm-stat-strip');
    expect(hero).toBeTruthy();
    expect(strip).toBeTruthy();
    const children = Array.from(fixtureHost(fixture).children);
    expect(children.indexOf(hero as Element)).toBeLessThan(children.indexOf(strip as Element));
  });

  it('renders stat strip, three rails, and the downloads section', () => {
    fixture.detectChanges();
    const root = fixtureHost(fixture);

    expect(root.querySelector('h1')?.textContent).toContain('Dashboard');
    expect(root.querySelector('mm-stat-strip')).toBeTruthy();

    const headings = Array.from(root.querySelectorAll('.rail-head h2')).map((node) => node.textContent.trim());
    expect(headings).toEqual(['Continue Watching', 'Trending Now', 'Recently Added']);
    expect(root.querySelector('#downloads h2')?.textContent).toContain('Downloads');
    expect(root.querySelector('[data-testid="dashboard-grid"]')).toBeNull();
  });

  it('renders continue-watching cards with art, subtitle, and progress', () => {
    fixture.detectChanges();
    const card = fixtureHost(fixture).querySelector('[data-testid="cw-rail"] .cw-card');
    expect(card?.getAttribute('href')).toContain('details?id=e1');
    expect(card?.textContent).toContain('Night Watch');
    expect(card?.textContent).toContain('S01E01 · Pilot');
    const art = card?.querySelector('.cw-card__art') as HTMLElement;
    expect(art.style.background).toContain('Thumb');
    const bar = card?.querySelector('.cw-bar i') as HTMLElement;
    expect(bar.style.width).toBe('64%');
  });

  it('keeps Demo gradients as gradients instead of treating them as image URLs', () => {
    watchNext.items.set([watchNextItem({ thumbUrl: 'linear-gradient(90deg, #123, #456)' })]);
    fixture.detectChanges();

    expect((fixtureHost(fixture).querySelector('.cw-card__art') as HTMLElement).style.background).toContain(
      'linear-gradient',
    );
  });

  it('shows an empty state for continue watching when nothing is in progress', () => {
    watchNext.status.set('empty');
    watchNext.items.set([]);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('[data-testid="cw-rail"] mm-state-card')?.textContent).toContain(
      'Nothing in progress',
    );
  });

  it('renders trending posters with rail-local rank badges', () => {
    fixture.detectChanges();
    const posters = fixtureHost(fixture).querySelectorAll('[data-testid="trending-rail"] .poster-card');
    expect(posters).toHaveLength(2);
    expect(posters[0].querySelector('.poster-card__rank')?.textContent).toBe('1');
    expect(posters[1].querySelector('.poster-card__rank')?.textContent).toBe('2');
    expect(posters[1].textContent).toContain('Frontline');
    expect(posters[1].textContent).toContain('Film');
    expect((posters[0].querySelector('.poster-card__art') as HTMLElement).style.background).toContain('linear-gradient');
  });

  it('renders recently added landscape cards', () => {
    fixture.detectChanges();
    const card = fixtureHost(fixture).querySelector('[data-testid="recent-rail"] .cw-card');
    expect(card?.textContent).toContain('After Us');
    expect(card?.textContent).toContain('2026 · Series');
  });

  it('renders the downloads queue with per-item pause and pause-all actions', () => {
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    expect(root.querySelector('#downloads .dl-item')?.textContent).toContain('Signal Drift');

    const pauseItem = root.querySelector('#downloads .dl-item mm-icon-button button') as HTMLButtonElement;
    pauseItem.click();
    expect(downloads['runTorrentAction']).toHaveBeenCalledWith('a', 'pause');

    const pauseAll = root.querySelector('[data-testid="downloads-pause-all"] button') as HTMLButtonElement;
    pauseAll.click();
    expect(downloads['runAction']).toHaveBeenCalledWith('pause');
  });

  it('starts downloads polling on create and stops it on destroy; shell facades stay untouched', () => {
    fixture.detectChanges();
    expect(downloads['startPolling']).toHaveBeenCalledTimes(1);
    expect(trending.refresh).not.toHaveBeenCalled();
    expect(storage['startPolling']).toBeUndefined();

    fixture.destroy();
    expect(downloads['stopPolling']).toHaveBeenCalledTimes(1);
  });

  it('refreshes all dashboard facades from onRefresh', () => {
    fixture.detectChanges();
    fixture.componentInstance.onRefresh();
    for (const facade of [health, libraryStats, libraryItems, watchNext, trending, downloads, storage, calendar, automation, activity]) {
      expect(facade.refresh).toHaveBeenCalledTimes(1);
    }
  });

  it('resolves dashboard media links, preserves explicit hrefs, and leaves unavailable items inert', () => {
    watchNext.items.set([watchNextItem({ href: null })]);
    libraryItems.items.set([libraryItem({ href: null })]);
    fixture.detectChanges();

    expect(fixtureHost(fixture).querySelector('[data-testid="cw-rail"] .cw-card')?.getAttribute('href')).toBe(
      'http://jf.local/web/index.html#!/details?id=e1',
    );
    expect(fixtureHost(fixture).querySelector('[data-testid="recent-rail"] .cw-card')?.getAttribute('href')).toBe(
      'http://jf.local/web/index.html#!/details?id=lib-1',
    );

    watchNext.items.set([watchNextItem({ href: 'http://explicit/episode' })]);
    libraryItems.items.set([libraryItem({ href: 'http://explicit/series' })]);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('[data-testid="cw-rail"] .cw-card')?.getAttribute('href')).toBe(
      'http://explicit/episode',
    );
    expect(fixtureHost(fixture).querySelector('[data-testid="recent-rail"] .cw-card')?.getAttribute('href')).toBe(
      'http://explicit/series',
    );

    watchNext.items.set([watchNextItem({ id: 'unknown', href: null, playable: false })]);
    libraryItems.items.set([libraryItem({ id: 'unknown', href: null, playable: false })]);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('[data-testid="cw-rail"] .cw-card')?.getAttribute('href')).toBeNull();
    expect(fixtureHost(fixture).querySelector('[data-testid="recent-rail"] .cw-card')?.getAttribute('href')).toBeNull();
  });
});
