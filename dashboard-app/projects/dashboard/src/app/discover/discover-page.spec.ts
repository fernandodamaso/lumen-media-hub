import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { DiscoverSourceTab, JellyseerrDiscoverKind, TraktDiscoverType } from './discover.models';
import { DiscoverCardItem, DiscoverHistoryFilter } from './discover-format';
import { DISCOVER_BATCH_SIZE, DiscoverPage } from './discover-page';
import { DiscoverFacade, DiscoverStatus, HermesView } from './discover.facade';

describe('DiscoverPage', () => {
  let fixture: ComponentFixture<DiscoverPage>;
  let facade: ReturnType<typeof createFacade>;

  beforeEach(() => {
    facade = createFacade();
    TestBed.configureTestingModule({
      imports: [DiscoverPage],
      providers: [{ provide: DiscoverFacade, useValue: facade }],
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
    expect(fixtureHost(fixture).textContent).toContain('Browse Hermes');

    clickTab('Jellyseerr');
    expect(facade.setTab).toHaveBeenCalledWith('jellyseerr');
  });

  it('renders the preserved Hermes History card with an In library badge', () => {
    facade.status.set('ready');
    facade.tab.set('hermes');
    facade.visibleItems.set([
      card({ title: 'The Bear', inLibrary: true, excludedReason: 'in_library' }),
    ]);
    fixture.detectChanges();

    clickHermesView('History');
    facade.hermesView.set('history');
    fixture.detectChanges();

    expect(facade.setHermesView).toHaveBeenCalledWith('history');
    expect(fixtureHost(fixture).textContent).toContain('The Bear');
    expect(fixtureHost(fixture).textContent).toContain('In library');
  });

  it('renders a Watched on Trakt badge for automatic watched projection', () => {
    facade.status.set('ready');
    facade.tab.set('hermes');
    facade.visibleItems.set([
      card({ title: 'The Bear', watchedOnTrakt: true, excludedReason: 'watched_on_trakt' }),
    ]);
    fixture.detectChanges();

    expect(fixtureHost(fixture).textContent).toContain('Watched on Trakt');
    expect(fixtureHost(fixture).textContent).not.toContain('In library');
  });

  it('keeps Request in the footer for every source and only mounts Hermes feedback', () => {
    facade.status.set('ready');
    facade.visibleItems.set([card({ title: 'Signal Drift' })]);
    fixture.detectChanges();

    for (const source of [
      { label: 'Hermes', hasFeedback: true },
      { label: 'Jellyseerr', hasFeedback: false },
      { label: 'Trakt', hasFeedback: false },
    ] as const) {
      clickTab(source.label);
      fixture.detectChanges();

      const root = fixtureHost(fixture);
      const request = root.querySelector('.discover-card__footer mm-button button');
      expect(request).toBeTruthy();
      expect(request?.textContent).toContain('Request');
      const overlay = root.querySelector('.discover-card__overlay');
      if (source.hasFeedback) {
        expect(overlay).toBeTruthy();
      } else {
        expect(overlay).toBeNull();
      }
      expect(overlay ? overlay.contains(request) : false).toBe(false);
    }
  });

  it('disables request controls for unavailable items and keeps feedback separate', () => {
    facade.status.set('ready');
    facade.tab.set('hermes');
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
    expect(facade.requestItem).not.toHaveBeenCalled();
  });

  it('exposes source filters as labelled radio groups with roving focus', () => {
    facade.status.set('ready');
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const group = root.querySelector('[role="radiogroup"][aria-label="Discover sources"]') as HTMLElement;
    expect(group).toBeTruthy();

    const sourceButtons = sourceTabButtons();
    expect(sourceButtons.map((button) => button.textContent.trim())).toEqual([
      'Hermes',
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

  it('does not show a toolbar Refresh control on the Hermes tab', () => {
    facade.status.set('ready');
    facade.tab.set('hermes');
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
    facade.tab.set('hermes');
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

    clickHermesView('History');
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

  it('shows Request more only on Hermes', () => {
    facade.status.set('ready');
    facade.tab.set('hermes');
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('Request more');

    facade.tab.set('jellyseerr');
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).not.toContain('Request more');
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

function clickHermesView(label: string): void {
  const button = Array.from(document.querySelectorAll('[role="radio"]')).find((candidate) =>
    candidate.textContent.includes(label),
  );
  if (!(button instanceof HTMLButtonElement)) throw new Error(`Hermes view button not found: ${label}`);
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
    hermesId: 'item',
    feedback: null,
    requestState: null,
    inLibrary: false,
    watchedOnTrakt: false,
    ...overrides,
  };
}

function createFacade() {
  const tab = signal<DiscoverSourceTab>('hermes');
  const hermesView = signal<HermesView>('active');
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
  const visibleItems = signal<DiscoverCardItem[]>([]);

  return {
    tab,
    hermesView,
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
    visibleItems,
    setTab: vi.fn((value: DiscoverSourceTab) => {
      tab.set(value);
    }),
    setHermesView: vi.fn((value: HermesView) => {
      hermesView.set(value);
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
    requestItem: vi.fn(() => Promise.resolve()),
    requestMore: vi.fn(() => Promise.resolve()),
    isSyncFailed: () => false,
  };
}
