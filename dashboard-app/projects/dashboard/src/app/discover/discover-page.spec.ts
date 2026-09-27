import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { DiscoverSourceTab, JellyseerrDiscoverKind, TraktDiscoverType } from './discover.models';
import { DiscoverCardItem, DiscoverHistoryFilter } from './discover-format';
import { DISCOVER_BATCH_SIZE, DiscoverPage } from './discover-page';
import { DiscoverFacade, DiscoverStatus, AiPicksView } from './discover.facade';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';

describe('DiscoverPage', () => {
  let fixture: ComponentFixture<DiscoverPage>;
  let facade: ReturnType<typeof createFacade>;
  let requestMedia: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    facade = createFacade();
    requestMedia = vi.fn(() => Promise.resolve({
      ok: true,
      partial_success: false,
      jellyseerr_request_id: 701,
      request_status: 'requested',
      already_requested: false,
      dashboard_state_persisted: true,
      reconciliation_queued: false,
      message: 'Request submitted to Jellyseerr.',
    }));
    TestBed.configureTestingModule({
      imports: [DiscoverPage],
      providers: [
        { provide: DiscoverFacade, useValue: facade },
        {
          provide: MEDIA_STACK_API,
          useValue: {
            getTvSeasons: vi.fn((tmdbId: number) => Promise.resolve({
              tmdbId,
              title: 'Shared dialog fixture',
              seasons: [
                { seasonNumber: 0, name: 'Specials', episodeCount: 2, airDate: null },
                { seasonNumber: 1, name: 'Season 1', episodeCount: 8, airDate: '2025-01-01' },
              ],
            })),
            requestMedia,
          },
        },
      ],
    });
    TestBed.overrideComponent(DiscoverPage, {
      set: { providers: [{ provide: DiscoverFacade, useValue: facade }] },
    });
    fixture = TestBed.createComponent(DiscoverPage);
  });

  it('switches source tabs through the facade', () => {
    facade.status.set('ready');
    facade.visibleItems.set([card({ title: 'Signal Drift' })]);
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('Browse AI Picks');

    clickTab('Jellyseerr');
    expect(facade.setTab).toHaveBeenCalledWith('jellyseerr');
  });

  it('renders the preserved AI Picks History card with an In library badge', () => {
    facade.status.set('ready');
    facade.tab.set('ai-picks');
    facade.visibleItems.set([
      card({ title: 'The Bear', inLibrary: true, excludedReason: 'in_library' }),
    ]);
    fixture.detectChanges();

    clickAiPicksView('History');
    facade.aiPicksView.set('history');
    fixture.detectChanges();

    expect(facade.setAiPicksView).toHaveBeenCalledWith('history');
    expect(fixtureHost(fixture).textContent).toContain('The Bear');
    expect(fixtureHost(fixture).textContent).toContain('In library');
  });

  it('renders a Watched on Trakt badge for automatic watched projection', () => {
    facade.status.set('ready');
    facade.tab.set('ai-picks');
    facade.visibleItems.set([
      card({ title: 'The Bear', watchedOnTrakt: true, excludedReason: 'watched_on_trakt' }),
    ]);
    fixture.detectChanges();

    expect(fixtureHost(fixture).textContent).toContain('Watched on Trakt');
    expect(fixtureHost(fixture).textContent).not.toContain('In library');
  });

  it('renders the watched snapshot warning for AI Picks', () => {
    facade.status.set('ready');
    facade.notice.set('Watched filtering is using a cached snapshot.');
    fixture.detectChanges();

    expect(fixtureHost(fixture).textContent).toContain('Watched filtering is using a cached snapshot.');
  });

  it('renders the complete AI Picks unavailable message', () => {
    facade.status.set('ready');
    facade.notice.set('Watched filtering is unavailable. Showing AI Picks recommendations.');
    fixture.detectChanges();

    expect(fixtureHost(fixture).textContent).toContain(
      'Watched filtering is unavailable. Showing AI Picks recommendations.',
    );
    expect(fixtureHost(fixture).textContent).not.toContain('Showing Trakt recommendations');
  });

  it('keeps Request in the footer for every source and only mounts AI Picks feedback', () => {
    facade.status.set('ready');
    facade.visibleItems.set([card({ title: 'Signal Drift' })]);
    fixture.detectChanges();

    for (const source of [
      { label: 'AI Picks', hasFeedback: true },
      { label: 'Jellyseerr', hasFeedback: false },
      { label: 'Trakt', hasFeedback: false },
    ] as const) {
      clickTab(source.label);
      fixture.detectChanges();

      const root = fixtureHost(fixture);
      const request = root.querySelector('.discover-card__footer mm-button button');
      expect(request).toBeTruthy();
      expect(request?.textContent).toContain('Request');
      const overlay = root.querySelector('mm-poster-action-overlay');
      expect(overlay).toBeTruthy();
      const liked = overlay?.querySelector('button[aria-label="Liked"]');
      if (source.hasFeedback) {
        expect(liked).toBeTruthy();
      } else {
        expect(liked).toBeNull();
      }
      expect(overlay ? overlay.contains(request) : false).toBe(false);
    }
  });

  it('opens the shared request dialog for movies and TV with season selection', async () => {
    facade.status.set('ready');
    facade.visibleItems.set([card({
      id: 'tv-missing',
      title: 'Shared TV',
      type: 'tv',
      tmdbId: 901,
      mediaStatus: 'missing',
    })]);
    fixture.detectChanges();

    const request = Array.from(fixtureHost(fixture).querySelectorAll('button')).find((button) =>
      button.textContent.trim() === 'Request',
    ) as HTMLButtonElement;
    request.click();
    fixture.detectChanges();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    fixture.detectChanges();

    expect(fixtureHost(fixture).querySelector('mm-media-request-dialog')).toBeTruthy();
    expect(fixtureHost(fixture).textContent).toContain('Choose seasons');
  });

  it('refreshes the active feed after the shared dialog completes a movie request', async () => {
    facade.status.set('ready');
    facade.visibleItems.set([card({
      id: 'movie-missing',
      title: 'Shared Movie',
      type: 'movie',
      tmdbId: 902,
      mediaStatus: 'missing',
    })]);
    fixture.detectChanges();

    clickAction('Request');
    fixture.detectChanges();
    clickAction('Add & search');
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    fixture.detectChanges();

    expect(requestMedia).toHaveBeenCalledWith({ mediaType: 'movie', mediaId: 902, aiPickId: 'item' });
    expect(facade.refreshActiveFeed).toHaveBeenCalledTimes(1);
  });

  it('opens the backend service link for an available title', async () => {
    const opened = vi.spyOn(window, 'open').mockImplementation(() => null);
    facade.status.set('ready');
    facade.visibleItems.set([card({
      id: 'movie-available',
      title: 'Available Movie',
      type: 'movie',
      tmdbId: 903,
      mediaStatus: 'available',
      service: 'jellyfin',
      serviceHref: 'https://jellyfin.example/item/903',
    })]);
    fixture.detectChanges();

    clickAction('Open in Jellyfin');
    await Promise.resolve();

    expect(opened).toHaveBeenCalledWith('https://jellyfin.example/item/903', '_blank', 'noreferrer');
    expect(fixtureHost(fixture).querySelector('mm-media-request-dialog')).toBeNull();
    opened.mockRestore();
  });

  it('disables request controls for unavailable items and keeps feedback separate', () => {
    facade.status.set('ready');
    facade.tab.set('ai-picks');
    facade.visibleItems.set([
      card({ id: 'no-tmdb', title: 'Untitled', tmdbId: 0 }),
      card({ id: 'eligible', title: 'Signal Drift', tmdbId: 101001 }),
    ]);
    fixture.detectChanges();

    const buttons = Array.from(fixtureHost(fixture).querySelectorAll('button'));
    const noTmdb = buttons.find((button) => button.textContent.includes('No TMDB ID'));
    if (!noTmdb) throw new Error('No TMDB ID button not found');
    expect(noTmdb.disabled).toBe(true);

    const liked = buttons.find((button) => button.getAttribute('aria-label') === 'Liked');
    if (!liked) throw new Error('Liked button not found');
    liked.click();
    expect(facade.submitFeedback).toHaveBeenCalledWith('no-tmdb', 'liked');
  });

  it('exposes source filters as labelled radio groups with roving focus', () => {
    facade.status.set('ready');
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const group = root.querySelector('[role="radiogroup"][aria-label="Discover sources"]') as HTMLElement;
    expect(group).toBeTruthy();

    const sourceButtons = sourceTabButtons();
    expect(sourceButtons.map((button) => button.textContent.trim())).toEqual([
      'AI Picks',
      'Jellyseerr',
      'Trakt',
    ]);
    expect(sourceButtons.every((button) => button.type === 'button')).toBe(true);
    expect(sourceButtons[0].getAttribute('aria-checked')).toBe('true');
    expect(sourceButtons[1].getAttribute('aria-checked')).toBe('false');
    expect(sourceButtons[0].getAttribute('role')).toBe('radio');

    sourceButtons[1].focus();
    expect(document.activeElement).toBe(sourceButtons[1]);
    sourceButtons[1].click();
    fixture.detectChanges();
    expect(facade.setTab).toHaveBeenCalledWith('jellyseerr');

    facade.tab.set('jellyseerr');
    fixture.detectChanges();
    expect(sourceTabButtons()[1].getAttribute('aria-checked')).toBe('true');
    expect(sourceTabButtons()[0].getAttribute('aria-checked')).toBe('false');
  });

  it('filters cards with search and updates the result count', () => {
    facade.status.set('ready');
    facade.visibleItems.set([
      card({ id: 'a', title: 'Alpha' }),
      card({ id: 'b', title: 'Beta' }),
    ]);
    fixture.detectChanges();

    setSearchInput('alpha');
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('1 match');
    expect(fixtureHost(fixture).querySelector('.discover-count')?.getAttribute('aria-live')).toBe('polite');
    expect(fixtureHost(fixture).querySelectorAll('mm-discover-card')).toHaveLength(1);

    setSearchInput('');
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('2 titles');
  });

  it('caps the initial grid at 24 items and loads more in batches', () => {
    facade.status.set('ready');
    facade.visibleItems.set(
      Array.from({ length: 30 }, (_, index) => card({ id: `item-${index}`, title: `Title ${index}` })),
    );
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelectorAll('mm-discover-card')).toHaveLength(24);

    clickLoadMore();
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelectorAll('mm-discover-card')).toHaveLength(30);
  });

  it('labels load more with the remaining batch size', () => {
    facade.status.set('ready');
    facade.visibleItems.set(
      Array.from({ length: 25 }, (_, index) => card({ id: `item-${index}`, title: `Title ${index}` })),
    );
    fixture.detectChanges();
    const loadMore = Array.from(document.querySelectorAll('button')).find((button) =>
      button.textContent.includes('Load'),
    );
    expect(loadMore?.textContent).toContain('Load 1 more');
  });

  it('resets the visible limit when the source tab changes', () => {
    facade.status.set('ready');
    facade.visibleItems.set(
      Array.from({ length: 30 }, (_, index) => card({ id: `item-${index}`, title: `Title ${index}` })),
    );
    fixture.detectChanges();
    clickLoadMore();
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelectorAll('mm-discover-card')).toHaveLength(30);

    clickTab('Jellyseerr');
    facade.tab.set('jellyseerr');
    fixture.detectChanges();
    expect(fixture.componentInstance.visibleLimit()).toBe(DISCOVER_BATCH_SIZE);
  });

  it('resets the visible limit when search changes', () => {
    facade.status.set('ready');
    facade.visibleItems.set(
      Array.from({ length: 30 }, (_, index) => card({ id: `item-${index}`, title: `Title ${index}` })),
    );
    fixture.detectChanges();
    clickLoadMore();
    fixture.detectChanges();
    setSearchInput('Title 1');
    fixture.detectChanges();
    expect(fixture.componentInstance.visibleLimit()).toBe(DISCOVER_BATCH_SIZE);
  });

  it('keeps the search query when switching sources', () => {
    facade.status.set('ready');
    facade.visibleItems.set([card({ title: 'Alpha' })]);
    fixture.detectChanges();
    setSearchInput('alpha');
    fixture.detectChanges();

    clickTab('Jellyseerr');
    facade.tab.set('jellyseerr');
    fixture.detectChanges();

    const input = document.querySelector('#discover-search-input');
    expect(input instanceof HTMLInputElement && input.value).toBe('alpha');
  });

  it('does not show a title count when the source is empty', () => {
    facade.status.set('empty');
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('.discover-count')).toBeNull();
  });

  it('renders disabled Jellyseerr as unavailable without an actionable retry', () => {
    facade.status.set('disabled');
    facade.tab.set('jellyseerr');
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('Jellyseerr unavailable');
    expect(root.textContent).toContain('Enable the requests profile');
    expect(root.textContent).toContain('JELLYSEERR_ENABLED=true');
    expect(root.textContent).not.toContain('Try again');
  });

  it('does not show a toolbar Refresh control on the AI Picks tab', () => {
    facade.status.set('ready');
    facade.tab.set('ai-picks');
    facade.visibleItems.set([card({ title: 'Signal Drift' })]);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const refreshButtons = Array.from(root.querySelectorAll('button')).filter((button) =>
      button.textContent.trim() === 'Refresh',
    );
    expect(refreshButtons).toHaveLength(0);
  });

  it('resets the visible limit when source filters change but not on refresh', () => {
    facade.status.set('ready');
    facade.tab.set('ai-picks');
    facade.visibleItems.set(
      Array.from({ length: 30 }, (_, index) => card({ id: `item-${index}`, title: `Title ${index}` })),
    );
    fixture.detectChanges();
    clickLoadMore();
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelectorAll('mm-discover-card')).toHaveLength(30);

    fixture.componentInstance.refresh();
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelectorAll('mm-discover-card')).toHaveLength(30);

    clickAiPicksView('History');
    fixture.detectChanges();
    expect(fixture.componentInstance.visibleLimit()).toBe(DISCOVER_BATCH_SIZE);
  });

  it('differentiates search empty state from source empty state', () => {
    facade.status.set('empty');
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('No recommendations in this view.');

    facade.status.set('ready');
    facade.visibleItems.set([card({ title: 'Alpha' })]);
    fixture.detectChanges();
    setSearchInput('zzz');
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('No titles match');
    expect(fixtureHost(fixture).textContent).toContain('Clear search');
  });

  it('shows skeleton grid while loading and keeps controls visible', () => {
    facade.status.set('loading');
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    expect(root.querySelector('.discover-controls')).toBeTruthy();
    expect(root.querySelector('.discover-results__loading-status')?.textContent).toContain(
      'Loading recommendations',
    );
    expect(root.querySelector('.discover-card--skeleton')).toBeTruthy();
    expect(root.querySelector('mm-state-card')).toBeNull();
  });

  it('shows Generate more picks only on AI Picks', () => {
    facade.status.set('ready');
    facade.tab.set('ai-picks');
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('Generate more picks');

    facade.tab.set('jellyseerr');
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).not.toContain('Generate more picks');
  });
});

function setSearchInput(value: string): void {
  const input = document.querySelector('#discover-search-input');
  if (!(input instanceof HTMLInputElement)) throw new Error('Search input not found');
  input.value = value;
  input.dispatchEvent(new Event('input'));
}

function clickLoadMore(): void {
  const button = Array.from(document.querySelectorAll('button')).find((candidate) =>
    candidate.textContent.includes('Load'),
  );
  if (!(button instanceof HTMLButtonElement)) throw new Error('Load more button not found');
  button.click();
}

function clickAction(label: string): void {
  const button = Array.from(document.querySelectorAll('button')).find((candidate) =>
    candidate.textContent.trim() === label,
  );
  if (!(button instanceof HTMLButtonElement)) throw new Error(`Action button not found: ${label}`);
  button.click();
}

function clickAiPicksView(label: string): void {
  const button = Array.from(document.querySelectorAll('[role="radio"]')).find((candidate) =>
    candidate.textContent.includes(label),
  );
  if (!(button instanceof HTMLButtonElement)) throw new Error(`AI Picks view button not found: ${label}`);
  button.click();
}

function clickTab(label: string): void {
  const button = Array.from(document.querySelectorAll('button')).find((candidate) =>
    candidate.textContent.includes(label),
  );
  if (!(button instanceof HTMLButtonElement)) throw new Error(`Tab button not found: ${label}`);
  button.click();
}

function sourceTabButtons(): HTMLButtonElement[] {
  return Array.from(document.querySelectorAll('[role="radiogroup"][aria-label="Discover sources"] [role="radio"]'));
}

function card(overrides: Partial<DiscoverCardItem> = {}): DiscoverCardItem {
  return {
    id: 'item',
    title: 'Title',
    type: 'movie',
    tmdbId: 1,
    aiPickId: 'item',
    feedback: null,
    requestState: null,
    inLibrary: false,
    watchedOnTrakt: false,
    mediaStatus: 'missing',
    service: null,
    serviceHref: null,
    ...overrides,
  };
}

function createFacade() {
  const tab = signal<DiscoverSourceTab>('ai-picks');
  const aiPicksView = signal<AiPicksView>('active');
  const historyFilter = signal<DiscoverHistoryFilter>('all');
  const jellyseerrKind = signal<JellyseerrDiscoverKind>('trending');
  const traktType = signal<TraktDiscoverType>('movies');
  const status = signal<DiscoverStatus>('loading');
  const error = signal('');
  const notice = signal('');
  const noticeTone = signal<'success' | 'warning' | 'danger' | 'info'>('info');
  const busyItemId = signal<string | null>(null);
  const requestingMore = signal(false);
  const generationPending = signal(false);
  const generationEnabled = signal(true);
  const visibleItems = signal<DiscoverCardItem[]>([]);

  return {
    tab,
    aiPicksView,
    historyFilter,
    jellyseerrKind,
    traktType,
    status,
    error,
    notice,
    noticeTone,
    busyItemId,
    requestingMore,
    generationPending,
    generationEnabled,
    visibleItems,
    setTab: vi.fn((value: DiscoverSourceTab) => {
      tab.set(value);
    }),
    setAiPicksView: vi.fn((value: AiPicksView) => {
      aiPicksView.set(value);
    }),
    setHistoryFilter: vi.fn((value: DiscoverHistoryFilter) => {
      historyFilter.set(value);
    }),
    setJellyseerrKind: vi.fn((value: JellyseerrDiscoverKind) => {
      jellyseerrKind.set(value);
    }),
    setTraktType: vi.fn((value: TraktDiscoverType) => {
      traktType.set(value);
    }),
    submitFeedback: vi.fn(() => Promise.resolve()),
    requestMore: vi.fn(() => Promise.resolve()),
    refreshActiveFeed: vi.fn(() => Promise.resolve()),
    isSyncFailed: () => false,
  };
}
