import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { signal } from '@angular/core';
import { vi, type Mock } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { AutomationFacade } from '../automation/automation.facade';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { CalendarFacade } from '../calendar/calendar.facade';
import { DownloadsFacade } from '../downloads/downloads.facade';
import { LibraryItem } from '../library/library.models';
import { LibraryItemsFacade } from '../library/library-items.facade';
import { MEDIA_STACK_API, type MediaStackApi } from '../media-stack/media-stack-api';
import { WatchNextFacade } from '../library/watch-next.facade';
import { LibraryStatsFacade } from '../library/library-stats.facade';
import { ActivityFacade } from '../right-rail/activity.facade';
import { StorageFacade } from '../storage/storage.facade';
import { CommandPalette } from './command-palette';
import { TrendingFacade } from '../dashboard/trending.facade';
import { RecentlyAvailableFacade } from '../library/recently-available.facade';
import { MediaSearchItem, MediaSearchResult } from '../media-request/media-request.models';

describe('CommandPalette', () => {
  let fixture: ComponentFixture<CommandPalette>;
  let router: Router;
  let downloads: { runAction: ReturnType<typeof vi.fn>; refresh: ReturnType<typeof vi.fn> };
  let trending: { refresh: ReturnType<typeof vi.fn> };
  let recentlyAvailable: { refresh: ReturnType<typeof vi.fn> };
  let searchMedia: Mock<MediaStackApi['searchMedia']>;
  let requestMedia: ReturnType<typeof vi.fn>;
  let getTvSeasons: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    downloads = { runAction: vi.fn(() => Promise.resolve()), refresh: vi.fn(() => Promise.resolve()) };
    trending = { refresh: vi.fn(() => Promise.resolve()) };
    recentlyAvailable = { refresh: vi.fn(() => Promise.resolve()) };
    searchMedia = vi.fn<MediaStackApi['searchMedia']>(() => Promise.resolve(emptySearch()));
    requestMedia = vi.fn(() => Promise.resolve({
      ok: true,
      partial_success: false,
      jellyseerr_request_id: 77,
      request_status: 'requested',
      already_requested: false,
      dashboard_state_persisted: true,
      reconciliation_queued: false,
      message: 'Request submitted to Jellyseerr.',
    }));
    getTvSeasons = vi.fn(() => Promise.resolve({ tmdbId: 1, title: 'Fixture', seasons: [] }));
    const watchNextFacade = { items: signal([]), refresh: vi.fn() };
    TestBed.configureTestingModule({
      imports: [CommandPalette],
      providers: [
        provideRouter([{ path: '**', children: [] }]),
        { provide: WatchNextFacade, useValue: watchNextFacade },
        {
          provide: MEDIA_STACK_API,
          useValue: {
            listWatchNext: vi.fn(() => Promise.resolve({ items: [] })),
            searchMedia,
            getTvSeasons,
            requestMedia,
          },
        },
        {
          provide: LibraryItemsFacade,
          useValue: {
            items: signal<LibraryItem[]>([
              {
                id: 'm1',
                title: 'Moonrise',
                kind: 'movie',
                meta: '2024 · Movie',
                art: 'linear-gradient(#000, #111)',
                overview: '',
                href: null,
                artworkState: 'ok',
                playable: true,
                episodeCount: null,
                played: false,
              },
            ]),
            refresh: vi.fn(),
          },
        },
        { provide: ServiceHealthFacade, useValue: { refresh: vi.fn() } },
        { provide: LibraryStatsFacade, useValue: { refresh: vi.fn() } },
        { provide: DownloadsFacade, useValue: downloads },
        { provide: StorageFacade, useValue: { refresh: vi.fn() } },
        { provide: CalendarFacade, useValue: { refresh: vi.fn() } },
        { provide: AutomationFacade, useValue: { refresh: vi.fn() } },
        { provide: ActivityFacade, useValue: { refresh: vi.fn() } },
        { provide: TrendingFacade, useValue: trending },
        { provide: RecentlyAvailableFacade, useValue: recentlyAvailable },
      ],
    });
    fixture = TestBed.createComponent(CommandPalette);
    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows local matches immediately and starts remote search at exactly 250 ms', async () => {
    vi.useFakeTimers();
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    const input = fixtureHost(fixture).querySelector('input') as HTMLInputElement;
    input.value = 'mo';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(fixtureHost(fixture).textContent).toContain('Moonrise');
    expect(fixtureHost(fixture).textContent).toContain('Your Library');
    expect(searchMedia).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(249);
    expect(searchMedia).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(searchMedia).toHaveBeenCalledTimes(1);
    expect(searchMedia).toHaveBeenCalledWith('mo', expect.any(AbortSignal));
  });

  it('aborts superseded searches and ignores their late responses', async () => {
    vi.useFakeTimers();
    const first = Promise.withResolvers<MediaSearchResult>();
    const second = Promise.withResolvers<MediaSearchResult>();
    searchMedia
      .mockImplementationOnce((_query, signal) => {
        expect(signal).toBeDefined();
        expect(signal?.aborted).toBe(false);
        return first.promise;
      })
      .mockImplementationOnce(() => second.promise);
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    enterQuery('mo');
    await vi.advanceTimersByTimeAsync(250);
    const firstSignal = searchMedia.mock.calls[0][1] as AbortSignal;

    enterQuery('moon');
    expect(firstSignal.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(250);

    second.resolve(searchResult([mediaItem({ identity: 'movie:2', tmdbId: 2, title: 'Moon Current' })]));
    await Promise.resolve();
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('Moon Current');
    expect(fixtureHost(fixture).textContent).not.toContain('Moonrise');

    first.resolve(searchResult([mediaItem({ identity: 'movie:1', tmdbId: 1, title: 'Moon Stale' })]));
    await Promise.resolve();
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('Moon Current');
    expect(fixtureHost(fixture).textContent).not.toContain('Moon Stale');
  });

  it('never searches remotely for a one-character trimmed query', async () => {
    vi.useFakeTimers();
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    enterQuery(' m ');
    await vi.advanceTimersByTimeAsync(500);

    expect(searchMedia).not.toHaveBeenCalled();
  });

  it('groups authoritative lifecycle results and routes only actionable states', async () => {
    vi.useFakeTimers();
    const opened = vi.spyOn(window, 'open').mockImplementation(() => null);
    const openChange = vi.fn();
    fixture.componentInstance.openChange.subscribe(openChange);
    searchMedia.mockResolvedValue(searchResult([
      mediaItem({
        identity: 'movie:10',
        tmdbId: 10,
        title: 'Demo Available',
        status: 'available',
        service: 'jellyfin',
        serviceHref: 'https://jellyfin.example/title/10',
        jellyfinId: 'jf-10',
      }),
      mediaItem({
        identity: 'movie:11',
        tmdbId: 11,
        title: 'Demo Tracked',
        status: 'tracked',
        service: 'radarr',
        serviceHref: 'https://radarr.example/movie/11',
        monitored: true,
      }),
      mediaItem({ identity: 'movie:12', tmdbId: 12, title: 'Demo Requested', status: 'requested', requestId: 12 }),
      mediaItem({ identity: 'movie:13', tmdbId: 13, title: 'Demo Processing', status: 'processing', requestId: 13 }),
      mediaItem({ identity: 'movie:14', tmdbId: 14, title: 'Demo Missing' }),
      mediaItem({ identity: 'movie:15', tmdbId: 15, title: 'Demo Unknown', status: 'unknown' }),
    ]));
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    enterQuery('demo');
    await vi.advanceTimersByTimeAsync(250);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('Your Library');
    expect(root.textContent).toContain('Catalog');
    expect(root.textContent).toContain('Request submitted');
    expect(root.textContent).toContain('Acquisition in progress');
    expect(root.textContent).toContain('Status unavailable');
    for (const title of ['Demo Requested', 'Demo Processing', 'Demo Unknown']) {
      expect(option(title).getAttribute('aria-disabled')).toBe('true');
      option(title).click();
    }
    expect(openChange).not.toHaveBeenCalled();

    option('Demo Available').click();
    await Promise.resolve();
    expect(opened).toHaveBeenCalledWith('https://jellyfin.example/title/10', '_blank', 'noreferrer');
    expect(openChange).toHaveBeenLastCalledWith(false);

    openChange.mockClear();
    option('Demo Tracked').click();
    await Promise.resolve();
    expect(opened).toHaveBeenCalledWith('https://radarr.example/movie/11', '_blank', 'noreferrer');
    expect(openChange).toHaveBeenLastCalledWith(false);
    opened.mockRestore();
  });

  it('keeps linkless available and tracked results disabled on Enter', async () => {
    vi.useFakeTimers();
    const opened = vi.spyOn(window, 'open').mockImplementation(() => null);
    const openChange = vi.fn();
    fixture.componentInstance.openChange.subscribe(openChange);
    searchMedia.mockResolvedValue(searchResult([
      mediaItem({
        identity: 'movie:16',
        tmdbId: 16,
        title: 'Demo Available Linkless',
        status: 'available',
        service: 'jellyfin',
        serviceHref: null,
        jellyfinId: undefined,
      }),
      mediaItem({
        identity: 'movie:17',
        tmdbId: 17,
        title: 'Demo Tracked Linkless',
        status: 'tracked',
        service: 'radarr',
        serviceHref: null,
        monitored: true,
      }),
    ]));
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    enterQuery('demo');
    await vi.advanceTimersByTimeAsync(250);
    fixture.detectChanges();

    expect(option('Demo Available Linkless').getAttribute('aria-disabled')).toBe('true');
    expect(option('Demo Available Linkless').textContent).toContain('Jellyfin link unavailable');
    expect(option('Demo Tracked Linkless').getAttribute('aria-disabled')).toBe('true');
    expect(option('Demo Tracked Linkless').textContent).toContain('Radarr link unavailable');

    const input = fixtureHost(fixture).querySelector('input') as HTMLInputElement;
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(opened).not.toHaveBeenCalled();
    expect(router.url).toBe('/');
    expect(openChange).not.toHaveBeenCalled();
    opened.mockRestore();
  });

  it.each([
    ['disabled', true, 'Catalog search is disabled. Showing local library matches.'],
    ['unavailable', false, 'Catalog search is temporarily unavailable. Showing local library matches.'],
  ] as const)('keeps local matches when catalog search is %s', async (availability, ok, message) => {
    vi.useFakeTimers();
    searchMedia.mockResolvedValue({
      ok,
      availability,
      sources: { jellyseerr: availability },
      items: [],
      ...(ok ? {} : { error: 'private upstream detail' }),
    });
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    enterQuery('mo');
    await vi.advanceTimersByTimeAsync(250);
    fixture.detectChanges();

    expect(fixtureHost(fixture).textContent).toContain('Moonrise');
    const status = fixtureHost(fixture).querySelector('[data-testid="palette-search-status"]');
    expect(status?.textContent).toContain(message);
    expect(status?.getAttribute('aria-live')).toBe('polite');
    expect(fixtureHost(fixture).textContent).not.toContain('private upstream detail');
  });

  it('clamps the active index when authoritative results shrink the list', async () => {
    vi.useFakeTimers();
    searchMedia.mockResolvedValue(searchResult([
      mediaItem({ identity: 'movie:20', tmdbId: 20, title: 'Moon Remote' }),
    ]));
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    enterQuery('mo');
    fixture.componentInstance.activeIndex.set(99);

    await vi.advanceTimersByTimeAsync(250);
    fixture.detectChanges();

    expect(fixture.componentInstance.activeIndex()).toBe(0);
  });

  it('keeps the palette open and refetches the selected identity after a request', async () => {
    vi.useFakeTimers();
    const missing = mediaItem({ identity: 'movie:30', tmdbId: 30, title: 'Demo Missing' });
    const requested = mediaItem({
      ...missing,
      status: 'requested',
      requestId: 77,
    });
    searchMedia
      .mockResolvedValueOnce(searchResult([missing]))
      .mockResolvedValueOnce(searchResult([requested]));
    const openChange = vi.fn();
    fixture.componentInstance.openChange.subscribe(openChange);
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    enterQuery('demo');
    await vi.advanceTimersByTimeAsync(250);
    fixture.detectChanges();
    option('Demo Missing').click();
    fixture.detectChanges();

    expect(openChange).not.toHaveBeenCalled();
    expect(fixtureHost(fixture).textContent).toContain('Add to library');

    const submit = fixtureHost(fixture).querySelector(
      '[data-testid="media-request-submit"] button',
    ) as HTMLButtonElement;
    submit.click();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    fixture.detectChanges();

    expect(requestMedia).toHaveBeenCalledWith({ mediaType: 'movie', mediaId: 30 });
    expect(searchMedia).toHaveBeenCalledTimes(2);
    expect(searchMedia).toHaveBeenLastCalledWith('demo', expect.any(AbortSignal));
    expect(fixture.componentInstance.query()).toBe('demo');
    expect(option('Demo Missing').getAttribute('aria-disabled')).toBe('true');
    expect(openChange).not.toHaveBeenCalled();
  });

  it('preserves focus, keyboard, and listbox semantics across lifecycle results', async () => {
    vi.useFakeTimers();
    const opened = vi.spyOn(window, 'open').mockImplementation(() => null);
    searchMedia.mockResolvedValue(searchResult([
      mediaItem({ identity: 'movie:40', tmdbId: 40, title: 'Demo Requested', status: 'requested', requestId: 40 }),
      mediaItem({
        identity: 'movie:41',
        tmdbId: 41,
        title: 'Demo Available',
        status: 'available',
        service: 'jellyfin',
        serviceHref: 'https://jellyfin.example/title/41',
        jellyfinId: 'jf-41',
      }),
    ]));
    const openChange = vi.fn();
    fixture.componentInstance.openChange.subscribe(openChange);
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    await Promise.resolve();

    const input = fixtureHost(fixture).querySelector('input') as HTMLInputElement;
    expect(document.activeElement).toBe(input);
    enterQuery('demo');
    await vi.advanceTimersByTimeAsync(250);
    fixture.detectChanges();

    const listbox = fixtureHost(fixture).querySelector('[role="listbox"]') as HTMLElement;
    const options = [...listbox.querySelectorAll<HTMLElement>('[role="option"]')];
    expect(input.getAttribute('role')).toBe('combobox');
    expect(input.getAttribute('aria-controls')).toBe(listbox.id);
    expect(input.getAttribute('aria-activedescendant')).toBe(options[0].id);
    expect(options[0].getAttribute('aria-disabled')).toBe('true');

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(openChange).not.toHaveBeenCalled();

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    fixture.detectChanges();
    expect(input.getAttribute('aria-activedescendant')).toBe(options[1].id);
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await Promise.resolve();
    expect(opened).toHaveBeenCalledWith('https://jellyfin.example/title/41', '_blank', 'noreferrer');
    expect(openChange).toHaveBeenLastCalledWith(false);
    opened.mockRestore();
  });

  it('filters results and navigates on selection', async () => {
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('[data-testid="command-palette"]')).toBeTruthy();
    expect(root.textContent).toContain('Dashboard');
    expect(root.textContent).not.toContain('Moonrise');

    const input = root.querySelector('input') as HTMLInputElement;
    input.value = 'pause';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(root.textContent).toContain('Pause all');
    expect(root.textContent).not.toContain('Moonrise');

    const pause = [...root.querySelectorAll('.palette__item')].find((node) =>
      node.textContent.includes('Pause all'),
    ) as HTMLButtonElement;
    pause.click();
    await fixture.whenStable();
    expect(downloads.runAction).toHaveBeenCalledWith('pause');
  });

  it('requires two characters before searching library titles and caps matches', () => {
    const items = Array.from({ length: 60 }, (_, index) => ({
      id: `m${index}`,
      title: `Moonrise ${index}`,
      kind: 'movie' as const,
      meta: '2024 · Movie',
      art: 'linear-gradient(#000, #111)',
      overview: '',
      href: null,
      artworkState: 'ok' as const,
      playable: true,
    }));
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [CommandPalette],
      providers: [
        provideRouter([{ path: '**', children: [] }]),
        { provide: WatchNextFacade, useValue: { items: signal([]), refresh: vi.fn() } },
        {
          provide: MEDIA_STACK_API,
          useValue: { listWatchNext: vi.fn(() => Promise.resolve({ items: [] })) },
        },
        {
          provide: LibraryItemsFacade,
          useValue: { items: signal(items), refresh: vi.fn() },
        },
        { provide: ServiceHealthFacade, useValue: { refresh: vi.fn() } },
        { provide: LibraryStatsFacade, useValue: { refresh: vi.fn() } },
        { provide: DownloadsFacade, useValue: { runAction: vi.fn(() => Promise.resolve()), refresh: vi.fn() } },
        { provide: StorageFacade, useValue: { refresh: vi.fn() } },
        { provide: CalendarFacade, useValue: { refresh: vi.fn() } },
        { provide: AutomationFacade, useValue: { refresh: vi.fn() } },
        { provide: ActivityFacade, useValue: { refresh: vi.fn() } },
      ],
    });
    fixture = TestBed.createComponent(CommandPalette);
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    const input = fixtureHost(fixture).querySelector('input') as HTMLInputElement;
    input.value = 'm';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).not.toContain('Moonrise 0');

    input.value = 'moon';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    const libraryButtons = [...fixtureHost(fixture).querySelectorAll('.palette__item')].filter((node) =>
      node.textContent.includes('Library'),
    );
    expect(libraryButtons).toHaveLength(40);
    expect(fixtureHost(fixture).textContent).toContain('Moonrise 0');
    expect(fixtureHost(fixture).textContent).not.toContain('Moonrise 40');
  });

  it('resets query when opened via the open input', () => {
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    fixture.componentInstance.query.set('pause');
    fixture.componentInstance.searchStatus.set('Stale search status');
    fixture.detectChanges();

    fixture.componentRef.setInput('open', false);
    fixture.detectChanges();
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    expect(fixture.componentInstance.query()).toBe('');
    expect(fixture.componentInstance.activeIndex()).toBe(0);
    expect(fixture.componentInstance.searchStatus()).toBeNull();
  });

  it('opens and closes with keyboard shortcuts', () => {
    const openChange = vi.fn();
    fixture.componentInstance.openChange.subscribe(openChange);
    fixture.componentRef.setInput('open', false);
    fixture.detectChanges();

    fixture.componentInstance.onDocumentKeydown(
      new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }),
    );
    expect(openChange).toHaveBeenCalledWith(true);

    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    fixture.componentInstance.onDocumentKeydown(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(openChange).toHaveBeenCalledWith(false);
  });

  it('refreshes trending and newly available through the shared refresh path', async () => {
    const refresh = fixture.componentInstance.items().find((item) => item.id === 'action-refresh');
    await refresh?.run();
    expect(trending.refresh).toHaveBeenCalledTimes(1);
    expect(recentlyAvailable.refresh).toHaveBeenCalledTimes(1);
  });

  function enterQuery(value: string): void {
    const input = fixtureHost(fixture).querySelector('input') as HTMLInputElement;
    input.value = value;
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  function option(title: string): HTMLButtonElement {
    const match = [...fixtureHost(fixture).querySelectorAll<HTMLButtonElement>('[role="option"]')]
      .find((candidate) => candidate.textContent.includes(title));
    if (!match) throw new Error(`Option not found: ${title}`);
    return match;
  }
});

function emptySearch(): MediaSearchResult {
  return {
    ok: true,
    availability: 'available',
    sources: { jellyseerr: 'fresh' },
    items: [],
  };
}

function searchResult(items: MediaSearchItem[]): MediaSearchResult {
  return { ...emptySearch(), items };
}

function mediaItem(overrides: Partial<MediaSearchItem> = {}): MediaSearchItem {
  return {
    identity: 'movie:1',
    type: 'movie',
    tmdbId: 1,
    title: 'Catalog title',
    year: 2025,
    overview: '',
    posterUrl: null,
    status: 'missing',
    service: null,
    serviceHref: null,
    requestId: null,
    monitored: null,
    ...overrides,
  };
}
