import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { DiscoverSourceTab, JellyseerrDiscoverKind, TraktDiscoverType } from '../downloads/media-stack-api';
import { DiscoverCardItem, DiscoverHistoryFilter } from './discover-format';
import { DiscoverPage } from './discover-page';
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
    // Override page-level providers so the test double is used.
    TestBed.overrideComponent(DiscoverPage, {
      set: { providers: [{ provide: DiscoverFacade, useValue: facade }] },
    });
    fixture = TestBed.createComponent(DiscoverPage);
  });

  it('switches source tabs through the facade', () => {
    facade.status.set('ready');
    facade.visibleItems.set([card({ title: 'Signal Drift' })]);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Explore Hermes');

    clickTab('Jellyseerr');
    expect(facade.setTab).toHaveBeenCalledWith('jellyseerr');
  });

  it('disables request controls for unavailable items and keeps feedback separate', () => {
    facade.status.set('ready');
    facade.tab.set('hermes');
    facade.visibleItems.set([
      card({ id: 'no-tmdb', title: 'Untitled', tmdbId: 0 }),
      card({ id: 'eligible', title: 'Signal Drift', tmdbId: 101001 }),
    ]);
    fixture.detectChanges();

    const buttons = Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[];
    const noTmdb = buttons.find((button) => button.textContent?.includes('No TMDB ID'))!;
    expect(noTmdb.disabled).toBe(true);

    const liked = buttons.find((button) => button.textContent?.includes('Liked'))!;
    liked.click();
    expect(facade.submitFeedback).toHaveBeenCalledWith('no-tmdb', 'liked');
    expect(facade.requestItem).not.toHaveBeenCalled();
  });
});

function clickTab(label: string): void {
  const button = (Array.from(document.querySelectorAll('button')) as HTMLButtonElement[]).find((candidate) =>
    candidate.textContent?.includes(label),
  );
  button?.click();
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
  const syncFailed = new Set<string>();

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
    startPolling: vi.fn(),
    setTab: vi.fn((value: DiscoverSourceTab) => tab.set(value)),
    setHermesView: vi.fn((value: HermesView) => hermesView.set(value)),
    setHistoryFilter: vi.fn((value: DiscoverHistoryFilter) => historyFilter.set(value)),
    setJellyseerrKind: vi.fn((value: JellyseerrDiscoverKind) => jellyseerrKind.set(value)),
    setTraktType: vi.fn((value: TraktDiscoverType) => traktType.set(value)),
    refresh: vi.fn(async () => undefined),
    submitFeedback: vi.fn(async () => undefined),
    requestItem: vi.fn(async () => undefined),
    requestMore: vi.fn(async () => undefined),
    isSyncFailed: (itemOrId: DiscoverCardItem | string) =>
      typeof itemOrId === 'string' ? syncFailed.has(itemOrId) : syncFailed.has(itemOrId.id),
  };
}
