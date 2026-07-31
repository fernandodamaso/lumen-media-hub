import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { ExternalDiscover, ExternalDiscoverItem } from '../discover/discover.models';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { TrendingFacade } from './trending.facade';

function item(title: string, tmdbId: number): ExternalDiscoverItem {
  return { type: 'movie', title, year: 2026, tmdb_id: tmdbId, poster_url: null, rating: null };
}

function discover(items: ExternalDiscoverItem[]): ExternalDiscover {
  return { ok: true, items };
}

describe('TrendingFacade', () => {
  let listTraktDiscover: ReturnType<typeof vi.fn<(type: string) => Promise<ExternalDiscover>>>;

  function setup(): TrendingFacade {
    TestBed.configureTestingModule({
      providers: [TrendingFacade, { provide: MEDIA_STACK_API, useValue: { listTraktDiscover } }],
    });
    return TestBed.inject(TrendingFacade);
  }

  beforeEach(() => {
    listTraktDiscover = vi.fn<(type: string) => Promise<ExternalDiscover>>();
  });

  it('auto-loads trending on construction', async () => {
    listTraktDiscover.mockImplementation((type: string): Promise<ExternalDiscover> =>
      Promise.resolve(type === 'shows' ? discover([item('Show A', 1)]) : discover([item('Movie A', 11)])),
    );
    const facade = setup();
    await vi.waitFor(() => {
      expect(facade.status()).toBe('ready');
    });

    expect(listTraktDiscover).toHaveBeenCalledWith('shows', undefined);
    expect(listTraktDiscover).toHaveBeenCalledWith('movies', undefined);
    expect(facade.items().map((entry) => entry.title)).toEqual(['Show A', 'Movie A']);
  });

  it('interleaves trending shows and movies by rank', async () => {
    listTraktDiscover.mockImplementation((type: string): Promise<ExternalDiscover> =>
      Promise.resolve(
        type === 'shows'
          ? discover([item('Show A', 1), item('Show B', 2), item('Show C', 3)])
          : discover([item('Movie A', 11), item('Movie B', 12)]),
      ),
    );
    const facade = setup();
    await vi.waitFor(() => {
      expect(facade.status()).toBe('ready');
    });

    expect(facade.status()).toBe('ready');
    expect(facade.items().map((entry) => entry.title)).toEqual([
      'Show A',
      'Movie A',
      'Show B',
      'Movie B',
      'Show C',
    ]);
    expect(facade.items().map((entry) => entry.rank)).toEqual([1, 2, 3, 4, 5]);
    expect(facade.items()[0].type).toBe('tv');
    expect(facade.items()[1].type).toBe('movie');
  });

  it('stays ready on one source when the other fails', async () => {
    listTraktDiscover.mockImplementation((type: string): Promise<ExternalDiscover> =>
      Promise.resolve(
        type === 'shows'
          ? discover([item('Show A', 1)])
          : { ok: false, items: [], error: 'Trakt offline' },
      ),
    );
    const facade = setup();
    await facade.refresh({ initial: true });

    expect(facade.status()).toBe('ready');
    expect(facade.items().map((entry) => entry.title)).toEqual(['Show A']);
  });

  it('fails hard on initial load when both sources fail', async () => {
    listTraktDiscover.mockResolvedValue({ ok: false, items: [], error: 'Trakt offline' });
    const facade = setup();
    await facade.refresh({ initial: true });

    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');
    expect(facade.items()).toHaveLength(0);
  });

  it('retains last-good items when a background refresh fails', async () => {
    listTraktDiscover.mockImplementation((type: string): Promise<ExternalDiscover> =>
      Promise.resolve(type === 'shows' ? discover([item('Show A', 1)]) : discover([])),
    );
    const facade = setup();
    await facade.refresh({ initial: true });
    expect(facade.items()).toHaveLength(1);

    listTraktDiscover.mockResolvedValue({ ok: false, items: [], error: 'Trakt offline' });
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.items()).toHaveLength(1);
    expect(facade.error()).toContain('Showing last loaded results');
  });
});
