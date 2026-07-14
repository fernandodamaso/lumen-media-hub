import { ComponentFixture, TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { vi } from 'vitest';
import { LibraryItem } from './library.models';
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
    expect(fixture.nativeElement.querySelectorAll('.poster-skeleton').length).toBeGreaterThan(0);

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
        art: 'linear-gradient(145deg, #8b5a2b, #1a1410 70%)',
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

  it('uses the whole poster as the link and keeps unlinked titles visible', () => {
    facade.status.set('ready');
    facade.items.set([
      {
        id: 'jf-dune',
        title: 'Dune',
        kind: 'movie',
        meta: '2021 · Movie',
        art: 'linear-gradient(145deg, #8b5a2b, #1a1410 70%)',
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
    expect(cards[0].textContent).toContain('Dune');

    const links = Array.from(fixture.nativeElement.querySelectorAll('a.poster-card')) as HTMLAnchorElement[];
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute('href')).toBe('https://jellyfin.example/web/index.html#!/details?id=jf-dune');
    expect(links[0].getAttribute('target')).toBe('_blank');
    expect(fixture.nativeElement.textContent).toContain('Broken Signal');
    expect(fixture.nativeElement.querySelector('[data-artwork="failed"]')).toBeTruthy();
  });

  it('places View all in the card footer with the selected collection count', () => {
    facade.status.set('ready');
    facade.movieCount.set(12);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.mm-card__header .view-all')).toBeNull();
    const footerLink = fixture.nativeElement.querySelector('.mm-card__footer .view-all') as HTMLAnchorElement;
    expect(footerLink).toBeTruthy();
    expect(footerLink.getAttribute('href')).toBe('https://jellyfin.example/web/index.html#!/movies.html');
    expect(fixture.nativeElement.querySelector('.mm-card__footer .library-summary')?.textContent).toContain('12 movies');

    findTab('Series').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.mm-card__footer .library-summary')?.textContent).toContain('3 series');

    facade.kind.set('movie');
    facade.movieCount.set(1);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.mm-card__footer .library-summary')?.textContent).toContain('1 movie');
  });

  it('keeps the View all action available while collection content is loading', () => {
    fixture.detectChanges();

    const footerLink = fixture.nativeElement.querySelector('.mm-card__footer .view-all') as HTMLAnchorElement;
    expect(footerLink?.getAttribute('href')).toBe('https://jellyfin.example/web/index.html#!/movies.html');
  });

  it('limits the poster preview to two rows at normal and compact card widths', () => {
    fixture.detectChanges();
    const styles = componentStyles();

    expect(styles).toMatch(/\.poster-grid[\s\S]*grid-template-columns:\s*repeat\(auto-fill,\s*minmax\(124px,\s*1fr\)\)/);
    expect(styles).toMatch(/\.poster-card[^{]*:nth-child\(n\+17\)[^{]*\{\s*display:\s*none/);
    expect(styles).toMatch(/@container \(max-width: 639px\)[\s\S]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/);
    expect(styles).toMatch(/@container \(max-width: 639px\)[\s\S]*\.poster-card[^{]*:nth-child\(n\+10\)[^{]*\{\s*display:\s*none/);
    expect(styles).not.toContain('repeat(6');
    expect(styles).not.toContain('@container (min-width: 960px)');
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
  const viewAllHref = computed(() => 'https://jellyfin.example/web/index.html#!/movies.html');
  return {
    status,
    kind,
    items,
    movieCount,
    seriesCount,
    error,
    refresh,
    setKind,
    viewAllHref,
  };
}

function componentStyles(): string {
  return Array.from(document.querySelectorAll('style'))
    .map((node) => node.textContent ?? '')
    .join('\n');
}
