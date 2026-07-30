import { ComponentFixture, TestBed } from '@angular/core/testing';
import { JELLYFIN_LINK_BASES } from '../library.models';
import { WatchNextItem } from '../watch-next.models';
import { WatchNextGrid } from './watch-next-grid';
import { fixtureHost } from '../../../testing/fixture-host';

describe('WatchNextGrid', () => {
  let fixture: ComponentFixture<WatchNextGrid>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [WatchNextGrid],
      providers: [{ provide: JELLYFIN_LINK_BASES, useValue: { jellyfinBase: 'https://jellyfin.example' } }],
    });
    fixture = TestBed.createComponent(WatchNextGrid);
  });

  it('renders episode subtitles and progress bars', () => {
    fixture.componentRef.setInput('items', [episode('e1', 'The Expanse', 'S04E02 · Jetsam', 42)]);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('The Expanse');
    expect(root.textContent).toContain('S04E02 · Jetsam');
    expect(root.querySelector('[role="progressbar"]')).toBeTruthy();
    expect(root.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('42');
    const hit = root.querySelector('.poster__hit') as HTMLAnchorElement;
    expect(hit).toBeTruthy();
    expect(hit.getAttribute('aria-label')).toBe('Play The Expanse');
  });

  it('hides the progress bar at 0%', () => {
    fixture.componentRef.setInput('items', [
      episode('e0', 'The Blue Hour', 'S02E03 · Nightfall', 0),
    ]);
    fixture.detectChanges();

    expect(fixtureHost(fixture).querySelector('[role="progressbar"]')).toBeNull();
  });

  it('carousels past five items in compact mode', () => {
    const items = Array.from({ length: 6 }, (_, index) =>
      episode(`e${index}`, `Series ${index + 1}`, `S01E0${index + 1} · Pilot`, 0),
    );
    fixture.componentRef.setInput('items', items);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelectorAll('.poster')).toHaveLength(5);
    const next = root.querySelector('.poster-rail__nav--next') as HTMLButtonElement;
    next.click();
    fixture.detectChanges();
    expect(root.querySelectorAll('.poster')).toHaveLength(1);
    expect(root.textContent).toContain('Series 6');
  });
});

function episode(id: string, title: string, subtitle: string, progressPercent: number): WatchNextItem {
  return {
    id,
    parentId: 'series-1',
    title,
    subtitle,
    kind: 'episode',
    art: 'linear-gradient(145deg, #1e3a5f, #0b1220 70%)',
    artworkState: 'ok',
    href: null,
    playable: true,
    progressPercent,
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
