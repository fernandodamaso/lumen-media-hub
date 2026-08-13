import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { fixtureHost } from '../../../testing/fixture-host';
import { LibraryItem } from '../library.models';
import { LibraryItemsFacade, LibraryItemsStatus } from '../library-items.facade';
import { LibraryPage } from './library-page';

describe('LibraryPage', () => {
  let fixture: ComponentFixture<LibraryPage>;
  let facade: ReturnType<typeof createFacade>;

  beforeEach(() => {
    facade = createFacade();
    TestBed.configureTestingModule({
      imports: [LibraryPage],
      providers: [provideRouter([]), { provide: LibraryItemsFacade, useValue: facade }],
    });
    fixture = TestBed.createComponent(LibraryPage);
  });

  it('filters titles by kind', () => {
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
    expect(root.querySelector('h1')?.textContent).toContain('Library');
    expect(root.textContent).toContain('Moonrise');
    expect(root.textContent).toContain('Night Watch');

    const movies = [...root.querySelectorAll('[role="radio"]')].find((button) =>
      button.textContent.includes('Movies'),
    ) as HTMLButtonElement;
    movies.click();
    fixture.detectChanges();
    expect(root.textContent).toContain('Moonrise');
    expect(root.textContent).not.toContain('Night Watch');
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
    episodeCount: null,
    played: false,
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
