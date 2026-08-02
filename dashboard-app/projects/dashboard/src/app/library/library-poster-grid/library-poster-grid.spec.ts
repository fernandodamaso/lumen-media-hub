import { ComponentFixture, TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../../testing/fixture-host';
import { JELLYFIN_LINK_BASES, LibraryItem } from '../library.models';
import { LibraryPosterGrid } from './library-poster-grid';

describe('LibraryPosterGrid', () => {
  let fixture: ComponentFixture<LibraryPosterGrid>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [LibraryPosterGrid],
      providers: [
        { provide: JELLYFIN_LINK_BASES, useValue: { jellyfinBase: 'https://jellyfin.example' } },
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
    const poster = root.querySelector('mm-poster');
    const hit = poster?.querySelector('.mm-poster__hit') as HTMLAnchorElement;
    expect(poster).toBeTruthy();
    expect(hit.getAttribute('href')).toBe('https://jellyfin.example/web/index.html#!/details?id=m1');
    expect(hit.getAttribute('aria-label')).toBe('Play Moonrise');
    expect(poster?.querySelector('.mm-poster--caption-below')).toBeTruthy();
    expect(poster?.querySelector('.mm-poster__play-cue')).toBeTruthy();
  });

  it('renders an inert poster when a title is not playable', () => {
    fixture.componentRef.setInput('items', [
      { ...item('m2', 'Lost', ''), playable: false },
    ]);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const poster = root.querySelector('mm-poster');
    expect(poster).toBeTruthy();
    expect(poster?.querySelector('.mm-poster__hit')).toBeNull();
    expect(poster?.querySelector('.mm-poster__play-cue')).toBeNull();
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
  };
}
