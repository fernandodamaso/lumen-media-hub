import { TestBed } from '@angular/core/testing';
import { describe, expect, it, vi } from 'vitest';
import { CALENDAR_LINK_BASES } from './calendar/calendar.models';
import { mapTorrent } from './downloads/downloads-format';
import { LibraryManagerLinksFacade } from './library/library-manager-links.facade';
import { MEDIA_STACK_API } from './media-stack/media-stack-api';


describe('PR 55 regressions', () => {
  it('does not mark a still-downloading torrent complete after display rounding', () => {
    const mapped = mapTorrent({
      hash: 'a'.repeat(40),
      name: 'Almost there',
      state: 'downloading',
      progress: 0.9995,
      size: 1000,
      downloaded: 999,
      dlspeed: 1,
      upspeed: 0,
      eta: 1,
      category: 'tv',
      completionOn: null,
    });

    expect(mapped.progress).toBe(100);
    expect(mapped.completed).toBe(false);
  });

  it('uses year-qualified Arr links when same-kind titles collide', async () => {
    const api = {
      getArrLibrary: vi.fn().mockResolvedValue({
        ok: true,
        series: {},
        movies: {
          dune: 'wrong-fallback',
          'dune::1984': 'dune-1984',
          'dune::2021': 'dune-2021',
        },
      }),
    };
    TestBed.configureTestingModule({
      providers: [
        LibraryManagerLinksFacade,
        { provide: MEDIA_STACK_API, useValue: api },
        {
          provide: CALENDAR_LINK_BASES,
          useValue: { radarrBase: 'https://radarr.example', sonarrBase: 'https://sonarr.example' },
        },
      ],
    });
    const facade = TestBed.inject(LibraryManagerLinksFacade);
    await facade.refresh();

    expect(
      facade.resolveHref({ title: 'Dune', kind: 'movie', meta: '1984 · Movie' }),
    ).toBe('https://radarr.example/movie/dune-1984');
    expect(
      facade.resolveHref({ title: 'Dune', kind: 'movie', meta: '2021 · Movie' }),
    ).toBe('https://radarr.example/movie/dune-2021');
  });
});
