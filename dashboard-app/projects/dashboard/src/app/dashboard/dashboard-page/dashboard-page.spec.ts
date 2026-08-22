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
import { RecentlyAvailableFacade, RecentlyAvailableStatus } from '../../library/recently-available.facade';
import { RecentlyAvailableItem } from '../../library/recently-available.models';
import { WatchNextFacade, WatchNextStatus } from '../../library/watch-next.facade';
import { WatchNextItem } from '../../library/watch-next.models';
import { JELLYFIN_LINK_BASES, LibraryStats } from '../../library/library.models';
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

function recentlyAvailableItem(overrides: Partial<RecentlyAvailableItem> = {}): RecentlyAvailableItem {
  return {
    id: 'ra-ep-1',
    parentId: 'series-1',
    title: 'Saga of Tanya the Evil',
    subtitle: 'S02E05 · Lamb',
    kind: 'episode',
    availableAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    art: 'linear-gradient(#111, #222)',
    artworkState: 'ok',
    thumbUrl: 'http://jf/Items/series-1/Images/Thumb',
    href: 'http://jf.local/web/index.html#!/details?id=ra-ep-1',
    playable: true,
    year: 2026,
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
    href: 'https://trakt.tv/shows/wasteland',
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
    items: ReturnType<typeof signal<unknown[]>>;
    error: ReturnType<typeof signal<string>>;
    refresh: ReturnType<typeof vi.fn>;
  };
  let recentlyAvailable: {
    status: ReturnType<typeof signal<RecentlyAvailableStatus>>;
    items: ReturnType<typeof signal<RecentlyAvailableItem[]>>;
    error: ReturnType<typeof signal<string>>;
    refresh: ReturnType<typeof vi.fn>;
    startPolling: ReturnType<typeof vi.fn>;
    stopPolling: ReturnType<typeof vi.fn>;
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
      items: signal([]),
      error: signal(''),
      refresh: vi.fn(),
    };
    recentlyAvailable = {
      status: signal<RecentlyAvailableStatus>('ready'),
      items: signal<RecentlyAvailableItem[]>([recentlyAvailableItem()]),
      error: signal(''),
      refresh: vi.fn(),
      startPolling: vi.fn(),
      stopPolling: vi.fn(),
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
        { provide: RecentlyAvailableFacade, useValue: recentlyAvailable },
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
    expect(headings).toEqual(['Continue Watching', 'Newly Available', 'Trending in Trakt']);
    expect(root.querySelectorAll('[data-testid$="-rail"]')).toHaveLength(3);
    expect(root.querySelector('[data-testid="recent-rail"]')).toBeNull();
    expect(root.textContent).not.toContain('Recently Added');
    expect(root.querySelector('#downloads h2')?.textContent).toContain('Downloads');
    expect(root.querySelector('[data-testid="dashboard-grid"]')).toBeNull();
  });

  it('renders continue-watching cards with art, subtitle, and progress', () => {
    fixture.detectChanges();
    const card = fixtureHost(fixture).querySelector('[data-testid="cw-rail"] mm-media-card');
    expect(card?.querySelector('.mm-media-card__hit')?.getAttribute('href')).toContain('details?id=e1');
    expect(card?.textContent).toContain('Night Watch');
    expect(card?.textContent).toContain('S01E01 · Pilot');
    const art = card?.querySelector('.mm-media-card__art') as HTMLElement;
    expect(art.style.background).toContain('Thumb');
    const bar = card?.querySelector('.mm-media-card__progress .mm-progress__bar') as HTMLElement;
    expect(bar.style.width).toBe('64%');
  });

  it('hides continue-watching titles with 0% progress', () => {
    watchNext.status.set('ready');
    watchNext.items.set([
      watchNextItem({ id: 'unstarted', title: 'Unstarted', progressPercent: 0 }),
      watchNextItem({ id: 'started', title: 'Started', progressPercent: 12 }),
    ]);
    watchNext.totalCount.set(2);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const cards = root.querySelectorAll('[data-testid="cw-rail"] mm-media-card');
    expect(cards).toHaveLength(1);
    expect(cards[0].textContent).toContain('Started');
    expect(cards[0].textContent).not.toContain('Unstarted');
    expect(root.querySelector('[data-testid="cw-rail"] .count')?.textContent).toBe('1 in progress');
  });

  it('shows empty continue-watching when every title is at 0% progress', () => {
    watchNext.status.set('ready');
    watchNext.items.set([watchNextItem({ progressPercent: 0 })]);
    watchNext.totalCount.set(1);
    fixture.detectChanges();

    expect(fixtureHost(fixture).querySelector('[data-testid="cw-rail"] mm-state-card')?.textContent).toContain(
      'Nothing in progress',
    );
  });

  it('keeps Demo gradients as gradients instead of treating them as image URLs', () => {
    watchNext.items.set([watchNextItem({ thumbUrl: 'linear-gradient(90deg, #123, #456)' })]);
    fixture.detectChanges();

    expect((fixtureHost(fixture).querySelector('.mm-media-card__art') as HTMLElement).style.background).toContain(
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

  it('renders shared clickable Trakt posters with rail-local ranks', () => {
    fixture.detectChanges();
    const posters = fixtureHost(fixture).querySelectorAll('[data-testid="trending-rail"] mm-media-card');
    expect(posters).toHaveLength(2);
    expect(posters[0].querySelector('.mm-media-card__tag')).toBeNull();
    expect(posters[1].textContent).toContain('Frontline');
    const link = posters[0].querySelector('.mm-media-card__hit') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('https://trakt.tv/shows/wasteland');
    expect(link.getAttribute('aria-label')).toBe('Open Wasteland on Trakt');
  });

  it('renders newly available landscape cards', () => {
    fixture.detectChanges();
    const card = fixtureHost(fixture).querySelector('[data-testid="newly-available-rail"] mm-media-card');
    expect(card?.textContent).toContain('Saga of Tanya the Evil');
    expect(card?.textContent).toContain('S02E05 · Lamb');
    expect(card?.textContent).toContain('Ready');
    expect(card?.querySelector('.mm-media-card__tag')?.textContent).toContain('NEW');
    expect(card?.querySelector('.mm-media-card__hit')?.getAttribute('aria-label')).toBe(
      'Open Saga of Tanya the Evil, S02E05, Lamb in Jellyfin',
    );
    expect(card?.querySelector('[role="progressbar"]')).toBeNull();
    expect(card?.querySelector('.mm-media-card__play-cue')).toBeNull();
  });

  it('renders movie newly available cards without year separator when year is missing', () => {
    recentlyAvailable.items.set([
      recentlyAvailableItem({
        kind: 'movie',
        parentId: null,
        title: 'Mickey 17',
        subtitle: '',
        year: null,
        availableAt: new Date(Date.now() - 30 * 60 * 60 * 1000).toISOString(),
      }),
    ]);
    fixture.detectChanges();
    const card = fixtureHost(fixture).querySelector('[data-testid="newly-available-rail"] mm-media-card');
    expect(card?.textContent).toContain('Mickey 17');
    expect(card?.textContent).toContain('Movie · Ready');
    expect(card?.querySelector('.mm-media-card__tag')).toBeNull();
    expect(card?.querySelector('.mm-media-card__hit')?.getAttribute('aria-label')).toBe(
      'Open Mickey 17 in Jellyfin',
    );
  });

  it('omits NEW for items exactly 24 hours old', () => {
    recentlyAvailable.items.set([
      recentlyAvailableItem({
        availableAt: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
      }),
    ]);
    fixture.detectChanges();
    const card = fixtureHost(fixture).querySelector('[data-testid="newly-available-rail"] mm-media-card');
    expect(card?.querySelector('.mm-media-card__tag')).toBeNull();
  });

  it('renders the downloads queue with per-item pause and pause-all actions', () => {
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    expect(root.querySelector('#downloads .dl-item')?.textContent).toContain('Signal Drift');
    expect(root.querySelector('#downloads .pill')?.classList.contains('pill--info')).toBe(true);

    const pauseItem = root.querySelector('#downloads .dl-item mm-icon-button button') as HTMLButtonElement;
    pauseItem.click();
    expect(downloads['runTorrentAction']).toHaveBeenCalledWith('a', 'pause');

    const pauseAll = root.querySelector('[data-testid="downloads-pause-all"] button') as HTMLButtonElement;
    pauseAll.click();
    expect(downloads['runAction']).toHaveBeenCalledWith('pause');
  });

  it('starts downloads and newly-available polling on create and stops on destroy', () => {
    fixture.detectChanges();
    expect(downloads['startPolling']).toHaveBeenCalledTimes(1);
    expect(recentlyAvailable.startPolling).toHaveBeenCalledTimes(1);
    expect(trending.refresh).not.toHaveBeenCalled();
    expect(storage['startPolling']).toBeUndefined();

    fixture.destroy();
    expect(downloads['stopPolling']).toHaveBeenCalledTimes(1);
    expect(recentlyAvailable.stopPolling).toHaveBeenCalledTimes(1);
  });

  it('refreshes all dashboard facades from onRefresh', () => {
    fixture.detectChanges();
    fixture.componentInstance.onRefresh();
    for (const facade of [health, libraryStats, libraryItems, watchNext, recentlyAvailable, trending, downloads, storage, calendar, automation, activity]) {
      expect(facade.refresh).toHaveBeenCalledTimes(1);
    }
  });

  it('resolves dashboard media links, preserves explicit hrefs, and leaves unavailable items inert', () => {
    watchNext.items.set([watchNextItem({ href: null })]);
    recentlyAvailable.items.set([recentlyAvailableItem({ href: null })]);
    fixture.detectChanges();

    expect(fixtureHost(fixture).querySelector('[data-testid="cw-rail"] .mm-media-card__hit')?.getAttribute('href')).toBe(
      'http://jf.local/web/index.html#!/details?id=e1',
    );
    expect(fixtureHost(fixture).querySelector('[data-testid="newly-available-rail"] .mm-media-card__hit')?.getAttribute('href')).toBe(
      'http://jf.local/web/index.html#!/details?id=ra-ep-1',
    );

    watchNext.items.set([watchNextItem({ href: 'http://explicit/episode' })]);
    recentlyAvailable.items.set([recentlyAvailableItem({ href: 'http://explicit/episode' })]);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('[data-testid="cw-rail"] .mm-media-card__hit')?.getAttribute('href')).toBe(
      'http://explicit/episode',
    );
    expect(fixtureHost(fixture).querySelector('[data-testid="newly-available-rail"] .mm-media-card__hit')?.getAttribute('href')).toBe(
      'http://explicit/episode',
    );

    watchNext.items.set([watchNextItem({ id: 'unknown', href: null, playable: false })]);
    recentlyAvailable.items.set([recentlyAvailableItem({ id: 'unknown', href: null })]);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('[data-testid="cw-rail"] .mm-media-card__hit')).toBeNull();
    expect(fixtureHost(fixture).querySelector('[data-testid="newly-available-rail"] .mm-media-card__hit')).toBeNull();
  });
});
