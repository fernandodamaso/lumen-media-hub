import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { DiscoverSourceTab, JellyseerrDiscoverKind, TraktDiscoverType } from './discover.models';
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
    expect(fixture.nativeElement.textContent).toContain('Browse Hermes');

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

    const buttons = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>);
    const noTmdb = buttons.find((button) => button.textContent.includes('No TMDB ID'));
    if (!noTmdb) throw new Error('No TMDB ID button not found');
    expect(noTmdb.disabled).toBe(true);

    const liked = buttons.find((button) => button.getAttribute('aria-label') === 'Liked');
    if (!liked) throw new Error('Liked button not found');
    liked.click();
    expect(facade.submitFeedback).toHaveBeenCalledWith('no-tmdb', 'liked');
    expect(facade.requestItem).not.toHaveBeenCalled();
  });

  it('exposes source tabs as pressed buttons in a labelled group', () => {
    facade.status.set('ready');
    fixture.detectChanges();

    const group = fixture.nativeElement.querySelector('.tabs') as HTMLElement;
    expect(group.getAttribute('role')).toBe('group');
    expect(group.getAttribute('aria-label')).toBe('Discover sources');
    expect(fixture.nativeElement.querySelector('[role="radio"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('[role="radiogroup"]')).toBeNull();

    const sourceButtons = sourceTabButtons();
    expect(sourceButtons.map((button) => button.textContent.trim())).toEqual([
      'Hermes',
      'Jellyseerr',
      'Trakt',
    ]);
    expect(sourceButtons.every((button) => button.type === 'button')).toBe(true);
    expect(sourceButtons[0].getAttribute('aria-pressed')).toBe('true');
    expect(sourceButtons[1].getAttribute('aria-pressed')).toBe('false');

    // Document order is focus/tab order for these native buttons.
    expect(sourceButtons[0].compareDocumentPosition(sourceButtons[1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(sourceButtons[1].compareDocumentPosition(sourceButtons[2]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    sourceButtons[1].focus();
    expect(document.activeElement).toBe(sourceButtons[1]);
    sourceButtons[1].click();
    fixture.detectChanges();
    expect(facade.setTab).toHaveBeenCalledWith('jellyseerr');

    facade.tab.set('jellyseerr');
    fixture.detectChanges();
    expect(sourceTabButtons()[1].getAttribute('aria-pressed')).toBe('true');
    expect(sourceTabButtons()[0].getAttribute('aria-pressed')).toBe('false');

    sourceButtons[2].focus();
    expect(document.activeElement).toBe(sourceButtons[2]);
    sourceButtons[2].click();
    expect(facade.setTab).toHaveBeenCalledWith('trakt');
  });
});

function clickTab(label: string): void {
  const button = (Array.from(document.querySelectorAll('button'))).find((candidate) =>
    candidate.textContent.includes(label),
  );
  button?.click();
}

function sourceTabButtons(): HTMLButtonElement[] {
  return Array.from(document.querySelectorAll('.tabs button.tab'));
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
    setTab: vi.fn((value: DiscoverSourceTab) => { tab.set(value); }),
    setHermesView: vi.fn((value: HermesView) => { hermesView.set(value); }),
    setHistoryFilter: vi.fn((value: DiscoverHistoryFilter) => { historyFilter.set(value); }),
    setJellyseerrKind: vi.fn((value: JellyseerrDiscoverKind) => { jellyseerrKind.set(value); }),
    setTraktType: vi.fn((value: TraktDiscoverType) => { traktType.set(value); }),
    submitFeedback: vi.fn(() => Promise.resolve()),
    requestItem: vi.fn(() => Promise.resolve()),
    requestMore: vi.fn(() => Promise.resolve()),
    isSyncFailed: () => false,
  };
}
