import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { fixtureHost } from '../../../testing/fixture-host';
import { LibraryItem } from '../library.models';
import { LibraryItemsFacade, LibraryItemsStatus } from '../library-items.facade';
import { LibraryCard } from './library-card';

describe('LibraryCard', () => {
  let fixture: ComponentFixture<LibraryCard>;
  let facade: ReturnType<typeof createFacade>;

  beforeEach(() => {
    facade = createFacade();
    TestBed.configureTestingModule({
      imports: [LibraryCard],
      providers: [provideRouter([]), { provide: LibraryItemsFacade, useValue: facade }],
    });
    fixture = TestBed.createComponent(LibraryCard);
  });

  it('renders series posters by default and switches to movies', () => {
    facade.status.set('ready');
    facade.items.set([
      item('m1', 'movie', 'Moonrise'),
      item('s1', 'series', 'Night Watch'),
    ]);
    facade.movieCount.set(1);
    facade.seriesCount.set(1);
    facade.totalCount.set(2);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('Night Watch');
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

  it('enters ready content inside card__inner with overlay skeleton markup', () => {
    facade.status.set('ready');
    facade.items.set([item('s1', 'series', 'Night Watch')]);
    facade.seriesCount.set(1);
    facade.totalCount.set(1);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.card__inner')).toBeTruthy();
    expect(root.querySelector('.card__skeleton')).toBeTruthy();
    expect(root.querySelector('.card__chrome-skeleton')).toBeTruthy();
    expect(root.querySelector('.card__foot-skeleton')).toBeTruthy();
    expect(root.querySelector('.mm-content-enter')).toBeNull();
  });

  it('keeps one poster row and carousels past five series', () => {
    facade.status.set('ready');
    facade.items.set([
      item('s1', 'series', 'Series One'),
      item('s2', 'series', 'Series Two'),
      item('s3', 'series', 'Series Three'),
      item('s4', 'series', 'Series Four'),
      item('s5', 'series', 'Series Five'),
      item('s6', 'series', 'Series Six'),
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
});

function item(id: string, kind: 'movie' | 'series', title: string): LibraryItem {
  return {
    id,
    title,
    kind,
    meta: kind === 'movie' ? '2024 · Movie' : '2024 · Series',
    art: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
    overview: '',
    href: null,
    artworkState: 'ok',
    playable: true,
  };
}

function createFacade() {
  return {
    status: signal<LibraryItemsStatus>('loading'),
    items: signal<LibraryItem[]>([]),
    error: signal(''),
    availability: signal<'complete' | 'partial'>('complete'),
    refreshing: signal(false),
    lastFetchedAt: signal(''),
    movieCount: signal(0),
    seriesCount: signal(0),
    totalCount: signal(0),
    refresh: vi.fn(),
  };
}
