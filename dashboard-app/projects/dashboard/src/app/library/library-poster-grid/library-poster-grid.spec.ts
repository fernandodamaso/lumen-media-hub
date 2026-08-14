import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { fixtureHost } from '../../../testing/fixture-host';
import { MmToastService } from '@app/ui';
import { JELLYFIN_LINK_BASES, LibraryItem } from '../library.models';
import { LibraryItemsFacade } from '../library-items.facade';
import { LibraryPosterGrid } from './library-poster-grid';

describe('LibraryPosterGrid', () => {
  let fixture: ComponentFixture<LibraryPosterGrid>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [LibraryPosterGrid],
      providers: [
        { provide: JELLYFIN_LINK_BASES, useValue: { jellyfinBase: 'https://jellyfin.example' } },
        {
          provide: LibraryItemsFacade,
          useValue: {
            setPlayed: vi.fn().mockResolvedValue(undefined),
            previewDeletion: vi.fn(),
            deleteItem: vi.fn(),
          },
        },
        { provide: MmToastService, useValue: { show: vi.fn() } },
      ],
    });
    fixture = TestBed.createComponent(LibraryPosterGrid);
  });

  it('uses a full-poster hit target when a title is playable', () => {
    fixture.componentRef.setInput('items', [
      item('m1', 'Moonrise', 'https://jellyfin.example/web/index.html#!/details?id=m1'),
    ]);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const poster = root.querySelector('mm-library-poster-card');
    const hit = poster?.querySelector('a[aria-label="Play Moonrise"]') as HTMLAnchorElement;
    expect(poster).toBeTruthy();
    expect(hit.getAttribute('href')).toBe('https://jellyfin.example/web/index.html#!/details?id=m1');
    expect(hit.classList.contains('mm-icon-button--overlay')).toBe(true);
    expect(poster?.querySelector('.library-poster-card__caption')).toBeTruthy();
    expect(poster?.querySelector('.mm-media-card__play-cue')).toBeNull();
    expect(poster?.querySelector('button[aria-label="Mark watched"]')).toBeTruthy();
    expect(poster?.querySelector('button[aria-label="Delete"]')).toBeTruthy();
  });

  it('renders an inert poster when a title is not playable', () => {
    fixture.componentRef.setInput('items', [
      { ...item('m2', 'Lost', ''), playable: false },
    ]);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const poster = root.querySelector('mm-library-poster-card');
    expect(poster).toBeTruthy();
    expect(poster?.querySelector('.mm-media-card__hit')).toBeNull();
    expect(poster?.querySelector('.mm-media-card__play-cue')).toBeNull();
  });
});

function item(id: string, title: string, href: string): LibraryItem {
  return {
    id,
    title,
    kind: 'movie',
    meta: '2024 · Movie',
    art: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
    overview: '',
    href,
    artworkState: 'ok',
    playable: true,
    episodeCount: null,
    played: false,
  };
}
