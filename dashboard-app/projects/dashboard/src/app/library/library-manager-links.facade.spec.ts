import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { CALENDAR_LINK_BASES } from '../calendar/calendar.models';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { LibraryManagerLinksFacade } from './library-manager-links.facade';

describe('LibraryManagerLinksFacade', () => {
  let api: { getArrLibrary: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    api = { getArrLibrary: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        LibraryManagerLinksFacade,
        { provide: MEDIA_STACK_API, useValue: api },
        {
          provide: CALENDAR_LINK_BASES,
          useValue: {
            sonarrBase: 'https://sonarr.example/',
            radarrBase: 'https://radarr.example/',
          },
        },
      ],
    });
  });

  it('resolves movies to Radarr and series to Sonarr with normalized titles', async () => {
    api.getArrLibrary.mockResolvedValue({
      ok: true,
      series: { 'the bear': 'the-bear' },
      movies: { dune: 'dune-2021' },
    });
    const facade = TestBed.inject(LibraryManagerLinksFacade);
    await facade.refresh();

    expect(facade.resolveHref({ title: ' DUNE ', kind: 'movie' })).toBe(
      'https://radarr.example/movie/dune-2021',
    );
    expect(facade.resolveHref({ title: 'The Bear', kind: 'series' })).toBe(
      'https://sonarr.example/series/the-bear',
    );
  });

  it('returns null for missing matches and failed Arr lookups', async () => {
    api.getArrLibrary.mockResolvedValue({
      ok: true,
      series: { dune: 'dune-series' },
      movies: { dune: 'dune-movie' },
    });
    const facade = TestBed.inject(LibraryManagerLinksFacade);
    await facade.refresh();
    expect(facade.resolveHref({ title: 'Missing', kind: 'movie' })).toBeNull();
    expect(facade.resolveHref({ title: 'Dune', kind: 'movie' })).toBe(
      'https://radarr.example/movie/dune-movie',
    );

    api.getArrLibrary.mockRejectedValue(new Error('offline'));
    await facade.refresh();
    expect(facade.resolveHref({ title: 'Dune', kind: 'movie' })).toBeNull();
  });
});
