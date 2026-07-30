import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { fixtureHost } from '../../../testing/fixture-host';
import { WatchNextItem } from '../watch-next.models';
import { WatchNextFacade, WatchNextStatus } from '../watch-next.facade';
import { LibraryCard } from './library-card';

describe('LibraryCard', () => {
  let fixture: ComponentFixture<LibraryCard>;
  let facade: ReturnType<typeof createFacade>;

  beforeEach(() => {
    facade = createFacade();
    TestBed.configureTestingModule({
      imports: [LibraryCard],
      providers: [provideRouter([]), { provide: WatchNextFacade, useValue: facade }],
    });
    fixture = TestBed.createComponent(LibraryCard);
  });

  it('renders series watch-next items by default and switches to movies', () => {
    facade.status.set('ready');
    facade.items.set([
      item('m1', 'movie', 'Moonrise'),
      item('e1', 'episode', 'Night Watch', 'S01E02 · Signal'),
    ]);
    facade.movieCount.set(1);
    facade.seriesCount.set(1);
    facade.totalCount.set(2);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('Night Watch');
    expect(root.textContent).toContain('S01E02 · Signal');
    expect(root.textContent).not.toContain('Moonrise');

    const moviesTab = [...root.querySelectorAll('.segmented__btn')].find((button) =>
      button.textContent.includes('Movies'),
    ) as HTMLButtonElement;
    moviesTab.click();
    fixture.detectChanges();
    expect(root.textContent).toContain('Moonrise');
    expect(root.textContent).not.toContain('Night Watch');
  });

  it('shows an error state with retry', () => {
    facade.status.set('error');
    facade.error.set('offline');
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('Library unavailable');
    fixture.componentInstance.retry();
    expect(facade.refresh).toHaveBeenCalledWith({ initial: true });
  });

  it('keeps the card heading visible while loading (D3)', () => {
    facade.status.set('loading');
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    const heading = root.querySelector('#library-heading');
    expect(heading).toBeTruthy();
    expect(heading?.textContent).toContain('Library');
  });

  it('keeps the library poster skeleton on one compact row while loading', () => {
    facade.status.set('loading');
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const skeletonMain = root.querySelector('.posters--skeleton.card__skeleton-main');
    if (!(skeletonMain instanceof HTMLElement)) {
      throw new Error('Expected poster skeleton container');
    }
    expect(skeletonMain.querySelectorAll('mm-skeleton')).toHaveLength(5);
    // Four stacked 180px posters would be ~720px; one compact row stays near one poster tall.
    expect(skeletonMain.scrollHeight).toBeLessThan(400);
  });

  it('enters ready content inside card__inner with overlay skeleton markup', () => {
    facade.status.set('ready');
    facade.items.set([item('e1', 'episode', 'Night Watch', 'S01E01 · Pilot')]);
    facade.seriesCount.set(1);
    facade.totalCount.set(1);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.card__inner')).toBeTruthy();
    expect(root.querySelector('.card__skeleton')).toBeTruthy();
    expect(root.querySelector('.card__chrome-skeleton')).toBeTruthy();
    expect(root.querySelector('.card__foot-skeleton')).toBeTruthy();
    expect(root.querySelector('.mm-content-enter')).toBeNull();
    expect(root.textContent).toContain('Your next items');
    expect(root.textContent).toContain('View full library');
  });

  it('keeps one poster row and carousels past five series', () => {
    facade.status.set('ready');
    facade.items.set([
      item('e1', 'episode', 'Series One', 'S01E01 · One'),
      item('e2', 'episode', 'Series Two', 'S01E01 · Two'),
      item('e3', 'episode', 'Series Three', 'S01E01 · Three'),
      item('e4', 'episode', 'Series Four', 'S01E01 · Four'),
      item('e5', 'episode', 'Series Five', 'S01E01 · Five'),
      item('e6', 'episode', 'Series Six', 'S01E01 · Six'),
    ]);
    facade.seriesCount.set(6);
    facade.totalCount.set(6);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelectorAll('.poster')).toHaveLength(5);
    expect(root.textContent).toContain('Series One');
    expect(root.textContent).not.toContain('Series Six');

    const next = root.querySelector('.poster-rail__nav--next') as HTMLButtonElement;
    expect(next).toBeTruthy();
    expect(root.querySelector('.poster-rail__nav-layer')).toBeTruthy();
    next.click();
    fixture.detectChanges();

    expect(root.querySelectorAll('.poster')).toHaveLength(1);
    expect(root.textContent).toContain('Series Six');
    expect(root.textContent).not.toContain('Series One');
  });

  it('shows global empty when there is nothing to watch', () => {
    facade.status.set('empty');
    facade.items.set([]);
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('Nothing waiting for you');
  });

  it('shows caught-up empty copy on the series tab', () => {
    facade.status.set('ready');
    facade.items.set([item('m1', 'movie', 'Moonrise')]);
    facade.movieCount.set(1);
    facade.seriesCount.set(0);
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain("You're caught up");
  });
});

function item(
  id: string,
  kind: 'movie' | 'episode',
  title: string,
  subtitle = '',
): WatchNextItem {
  return {
    id,
    parentId: kind === 'episode' ? 'series-1' : null,
    title,
    subtitle,
    kind,
    art: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
    artworkState: 'ok',
    href: null,
    playable: true,
    progressPercent: kind === 'movie' ? 12 : 0,
    year: null,
    rating: null,
    genres: [],
    overview: null,
    runtimeTicks: null,
    positionTicks: null,
    backdropUrl: null,
    thumbUrl: null,
  };
}

function createFacade() {
  return {
    status: signal<WatchNextStatus>('loading'),
    items: signal<WatchNextItem[]>([]),
    error: signal(''),
    refreshing: signal(false),
    lastFetchedAt: signal(''),
    movieCount: signal(0),
    seriesCount: signal(0),
    totalCount: signal(0),
    movies: signal<WatchNextItem[]>([]),
    series: signal<WatchNextItem[]>([]),
    refresh: vi.fn(),
  };
}
