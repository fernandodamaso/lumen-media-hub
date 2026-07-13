import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { LibraryItem, DEFAULT_LIBRARY_ART } from '../downloads/media-stack-api';
import { LibraryBoard } from './library-board';
import { LibraryFacade, LibraryStatus } from './library.facade';

describe('LibraryBoard', () => {
  let fixture: ComponentFixture<LibraryBoard>;
  let facade: ReturnType<typeof createFacade>;

  beforeEach(() => {
    facade = createFacade();
    TestBed.configureTestingModule({
      imports: [LibraryBoard],
      providers: [{ provide: LibraryFacade, useValue: facade }],
    });
    fixture = TestBed.createComponent(LibraryBoard);
  });

  it('renders loading, empty, and error states with retry recovery', async () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Loading library');

    facade.status.set('empty');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No movies in the demo library');

    facade.status.set('error');
    facade.error.set('Offline');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Offline');
    findButton('Try again').click();
    await fixture.whenStable();
    expect(facade.refresh).toHaveBeenCalled();
  });

  it('switches collections and keeps titles visible for missing or failed art', () => {
    facade.status.set('ready');
    facade.items.set([
      {
        id: 'jf-dune',
        title: 'Dune',
        kind: 'movie',
        meta: '2021 · Movie',
        art: DEFAULT_LIBRARY_ART,
        overview: 'Desert power.',
        href: 'https://jellyfin.example/web/index.html#!/details?id=jf-dune',
        artworkState: 'ok',
        playable: true,
      },
      {
        id: 'jf-night',
        title: 'Night Transit',
        kind: 'movie',
        meta: '2026 · Movie',
        art: 'linear-gradient(145deg, var(--mm-component-accent), var(--mm-component-card-bg) 65%)',
        overview: 'Missing art demo.',
        href: null,
        artworkState: 'missing',
        playable: true,
      },
    ]);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Dune');
    expect(fixture.nativeElement.textContent).toContain('Night Transit');
    expect(fixture.nativeElement.querySelector('[data-artwork="missing"]')).toBeTruthy();
    expect(fixture.nativeElement.textContent).toContain('Movies');
    expect(fixture.nativeElement.textContent).toContain('2');
    expect(fixture.nativeElement.textContent).toContain('Series');
    expect(fixture.nativeElement.textContent).toContain('3');

    findTab('Series').click();
    expect(facade.setKind).toHaveBeenCalledWith('series');
  });

  it('exposes a focusable DOM contract for disclosure without JS open state', () => {
    facade.status.set('ready');
    facade.items.set([
      {
        id: 'jf-dune',
        title: 'Dune',
        kind: 'movie',
        meta: '2021 · Movie',
        art: DEFAULT_LIBRARY_ART,
        overview: 'A mythic desert world.',
        href: 'https://jellyfin.example/web/index.html#!/details?id=jf-dune',
        artworkState: 'ok',
        playable: true,
      },
      {
        id: 'jf-failed',
        title: 'Broken Signal',
        kind: 'movie',
        meta: 'Series',
        art: 'linear-gradient(145deg, var(--mm-component-accent), var(--mm-component-card-bg) 65%)',
        overview: 'Failed art demo.',
        href: null,
        artworkState: 'failed',
        playable: true,
      },
    ] satisfies LibraryItem[]);
    fixture.detectChanges();

    const cards = Array.from(fixture.nativeElement.querySelectorAll('.poster-card')) as HTMLElement[];
    expect(cards).toHaveLength(2);
    expect(cards[0].tabIndex).toBe(0);
    expect(cards[0].classList.contains('poster-card--open')).toBe(false);
    expect(cards[0].querySelector('.poster-card__disclosure')?.textContent).toContain('A mythic desert world.');
    expect(cards[0].querySelector('mm-poster')?.textContent).toContain('Dune');

    const links = Array.from(fixture.nativeElement.querySelectorAll('a.poster-card__link')) as HTMLAnchorElement[];
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute('href')).toBe('https://jellyfin.example/web/index.html#!/details?id=jf-dune');
    expect(links[0].getAttribute('target')).toBe('_blank');
    expect(fixture.nativeElement.textContent).toContain('Broken Signal');
    expect(fixture.nativeElement.querySelector('[data-artwork="failed"]')).toBeTruthy();
  });

  function findButton(label: string): HTMLButtonElement {
    return (Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[]).find(
      (button) => button.textContent?.includes(label),
    ) as HTMLButtonElement;
  }

  function findTab(label: string): HTMLButtonElement {
    return (Array.from(fixture.nativeElement.querySelectorAll('.switcher__tab')) as HTMLButtonElement[]).find(
      (button) => button.textContent?.includes(label),
    ) as HTMLButtonElement;
  }
});

function createFacade() {
  const status = signal<LibraryStatus>('loading');
  const kind = signal<'movie' | 'series'>('movie');
  const items = signal<LibraryItem[]>([]);
  const movieCount = signal(2);
  const seriesCount = signal(3);
  const error = signal('');
  const refresh = vi.fn(async () => status.set('ready'));
  const setKind = vi.fn((next: 'movie' | 'series') => kind.set(next));
  return {
    status,
    kind,
    items,
    movieCount,
    seriesCount,
    error,
    refresh,
    setKind,
  };
}
