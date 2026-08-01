import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { JELLYFIN_LINK_BASES } from '../../library/library.models';
import { WatchNextFacade } from '../../library/watch-next.facade';
import { WatchNextItem } from '../../library/watch-next.models';
import {
  buildHeroView,
  formatRemainingLabel,
  formatRuntimeTicks,
  HeroFacade,
  selectHeroCandidate,
  splitTitleEmphasis,
} from './hero.facade';

const MINUTE_TICKS = 600_000_000;

function item(overrides: Partial<WatchNextItem>): WatchNextItem {
  return {
    id: 'id-1',
    parentId: null,
    title: 'Ashes of the Crown',
    subtitle: '',
    kind: 'movie',
    art: 'linear-gradient(#000, #111)',
    artworkState: 'ok',
    href: null,
    playable: true,
    progressPercent: 52,
    year: 2026,
    rating: 8.36,
    genres: ['Fantasy', 'Adventure', 'Drama'],
    overview: 'A deposed queen crosses the burned wastes.',
    runtimeTicks: 166 * MINUTE_TICKS,
    positionTicks: 85 * MINUTE_TICKS,
    backdropUrl: 'http://jf/Items/id-1/Images/Backdrop',
    thumbUrl: 'http://jf/Items/id-1/Images/Thumb',
    ...overrides,
  };
}

describe('hero rules', () => {
  it('selects the first watch-next item that is playable and has a backdrop', () => {
    const items = [
      item({ id: 'no-backdrop', backdropUrl: null }),
      item({ id: 'not-playable', playable: false }),
      item({ id: 'winner' }),
      item({ id: 'runner-up' }),
    ];
    expect(selectHeroCandidate(items)?.id).toBe('winner');
  });

  it('returns null when no candidate qualifies', () => {
    expect(selectHeroCandidate([item({ backdropUrl: null }), item({ playable: false })])).toBeNull();
    expect(selectHeroCandidate([])).toBeNull();
  });

  it('splits the last title word for gold italic emphasis', () => {
    expect(splitTitleEmphasis('Ashes of the Crown')).toEqual({ head: 'Ashes of the', tail: 'Crown' });
    expect(splitTitleEmphasis('Dune')).toEqual({ head: '', tail: 'Dune' });
    expect(splitTitleEmphasis('  The  Expanse  ')).toEqual({ head: 'The', tail: 'Expanse' });
  });

  it('formats runtime and remaining time from ticks', () => {
    expect(formatRuntimeTicks(166 * MINUTE_TICKS)).toBe('2h 46m');
    expect(formatRuntimeTicks(45 * MINUTE_TICKS)).toBe('45m');
    expect(formatRuntimeTicks(null)).toBe('');
    expect(formatRemainingLabel(166 * MINUTE_TICKS, 85 * MINUTE_TICKS)).toBe('1h 21m remaining');
    expect(formatRemainingLabel(null, 10 * MINUTE_TICKS)).toBe('');
    expect(formatRemainingLabel(80 * MINUTE_TICKS, 85 * MINUTE_TICKS)).toBe('');
  });

  it('builds a movie hero view with meta, overview, and play href', () => {
    const view = buildHeroView(item({}), { jellyfinBase: 'http://jf' });
    expect(view.titleParts).toEqual({ head: 'Ashes of the', tail: 'Crown' });
    expect(view.meta).toEqual(['2026', '★ 8.4', '2h 46m', 'Fantasy, Adventure']);
    expect(view.overview).toContain('deposed queen');
    expect(view.remainingLabel).toBe('1h 21m remaining');
    expect(view.playHref).toBe('http://jf/web/index.html#!/details?id=id-1');
  });

  it('displays a zero rating', () => {
    expect(buildHeroView(item({ rating: 0 }), {}).meta).toContain('★ 0.0');
  });

  it('presents series identity for episodes with the episode code in meta', () => {
    const view = buildHeroView(
      item({
        id: 'ep-9',
        parentId: 'series-1',
        kind: 'episode',
        title: 'The Shōgun Court',
        subtitle: 'S02E04 · The Red Banners',
        genres: ['Drama'],
      }),
      { jellyfinBase: 'http://jf/' },
    );
    // Series identity: the series title stays the hero title, backdrop/genres come from the series record.
    expect(view.title).toBe('The Shōgun Court');
    expect(view.meta[0]).toBe('S2 E4 · The Red Banners');
    expect(view.meta).toEqual(['S2 E4 · The Red Banners', '2026', '★ 8.4', '2h 46m', 'Drama']);
    expect(view.playHref).toBe('http://jf/web/index.html#!/details?id=ep-9');
  });
});

describe('HeroFacade', () => {
  it('derives the first qualifying watch-next item and hides otherwise', () => {
    const items = signal<WatchNextItem[]>([item({ backdropUrl: null })]);
    TestBed.configureTestingModule({
      providers: [
        { provide: WatchNextFacade, useValue: { items } },
        { provide: JELLYFIN_LINK_BASES, useValue: { jellyfinBase: 'http://jf' } },
      ],
    });
    const facade = TestBed.inject(HeroFacade);
    expect(facade.view()).toBeNull();

    items.set([item({ id: 'winner' }), item({ id: 'second' })]);
    expect(facade.view()?.id).toBe('winner');
  });

  it('uses only the first eligible item for the static hero', () => {
    const items = signal<WatchNextItem[]>([item({ id: 'first' }), item({ id: 'second' })]);
    TestBed.configureTestingModule({
      providers: [
        { provide: WatchNextFacade, useValue: { items } },
        { provide: JELLYFIN_LINK_BASES, useValue: { jellyfinBase: 'http://jf' } },
      ],
    });

    expect(TestBed.inject(HeroFacade).view()?.id).toBe('first');
  });
});
