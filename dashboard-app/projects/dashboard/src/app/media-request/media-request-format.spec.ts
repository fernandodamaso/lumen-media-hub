import {
  mapMediaRequestAction,
  mapMediaSearchResult,
  mapTvSeasonCollection,
} from './media-request-format';

const lifecycle = {
  status: 'missing',
  service: null,
  serviceHref: null,
  requestId: null,
  monitored: null,
} as const;

function validSearchItem(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    identity: 'movie:42',
    type: 'movie',
    tmdbId: 42,
    title: 'Arrival',
    year: 2016,
    overview: 'First contact.',
    posterUrl: 'https://image.tmdb.org/t/p/w342/arrival.jpg',
    ...lifecycle,
    ...overrides,
  };
}

describe('media request wire mappers', () => {
  it('maps a strict media search envelope and preserves typed lifecycle state', () => {
    const result = mapMediaSearchResult({
      ok: true,
      availability: 'available',
      sources: {
        jellyseerr: 'fresh',
        jellyfin: 'stale',
        radarr: 'fresh',
        sonarr: 'unavailable',
      },
      items: [
        validSearchItem(),
        validSearchItem({
          identity: 'tv:42',
          type: 'tv',
          status: 'processing',
          requestId: 91,
          year: null,
          posterUrl: null,
        }),
        validSearchItem({
          identity: 'movie:77',
          tmdbId: 77,
          status: 'tracked',
          service: 'radarr',
          serviceHref: 'https://radarr.example/movie/arrival',
          monitored: false,
        }),
      ],
    });

    expect(result).toEqual({
      ok: true,
      availability: 'available',
      sources: {
        jellyseerr: 'fresh',
        jellyfin: 'stale',
        radarr: 'fresh',
        sonarr: 'unavailable',
      },
      items: [
        validSearchItem(),
        validSearchItem({
          identity: 'tv:42',
          type: 'tv',
          status: 'processing',
          requestId: 91,
          year: null,
          posterUrl: null,
        }),
        validSearchItem({
          identity: 'movie:77',
          tmdbId: 77,
          status: 'tracked',
          service: 'radarr',
          serviceHref: 'https://radarr.example/movie/arrival',
          monitored: false,
        }),
      ],
      error: undefined,
    });
  });

  it('rejects malformed identities, enums, IDs, links, source health, and lifecycle combinations', () => {
    const malformed = [
      validSearchItem({ identity: 'tv:42' }),
      validSearchItem({ tmdbId: 0, identity: 'movie:0' }),
      validSearchItem({ status: 'queued' }),
      validSearchItem({ serviceHref: 'javascript:alert(1)' }),
      validSearchItem({ posterUrl: 'file:///private/poster.jpg' }),
      validSearchItem({ service: 'radarr' }),
      validSearchItem({ status: 'tracked', service: 'sonarr', monitored: true }),
    ];

    for (const item of malformed) {
      expect(() =>
        mapMediaSearchResult({
          ok: true,
          availability: 'available',
          sources: { jellyseerr: 'fresh' },
          items: [item],
        }),
      ).toThrow(/Malformed media search response/);
    }

    expect(() =>
      mapMediaSearchResult({
        ok: true,
        availability: 'available',
        sources: { jellyseerr: 'secret-state' },
        items: [],
      }),
    ).toThrow(/Malformed media search response/);
  });

  it('maps disabled and unavailable search envelopes without inventing results', () => {
    expect(
      mapMediaSearchResult({
        ok: true,
        availability: 'disabled',
        sources: { jellyseerr: 'disabled' },
        items: [],
      }),
    ).toEqual({
      ok: true,
      availability: 'disabled',
      sources: { jellyseerr: 'disabled' },
      items: [],
      error: undefined,
    });

    expect(
      mapMediaSearchResult({
        ok: false,
        availability: 'unavailable',
        sources: { jellyseerr: 'unavailable' },
        items: [],
        error: 'Media search is temporarily unavailable',
      }),
    ).toMatchObject({ ok: false, availability: 'unavailable', items: [] });
  });

  it('sorts exact TV seasons while preserving specials metadata', () => {
    expect(
      mapTvSeasonCollection(
        {
          ok: true,
          tmdbId: 42,
          title: 'The Show',
          seasons: [
            { seasonNumber: 2, name: 'Season 2', episodeCount: 8, airDate: '2025-01-01' },
            { seasonNumber: 0, name: 'Specials', episodeCount: 3, airDate: null },
            { seasonNumber: 1, name: 'Season 1', episodeCount: 10, airDate: '2024-01-01' },
          ],
        },
        42,
      ),
    ).toEqual({
      tmdbId: 42,
      title: 'The Show',
      seasons: [
        { seasonNumber: 0, name: 'Specials', episodeCount: 3, airDate: null },
        { seasonNumber: 1, name: 'Season 1', episodeCount: 10, airDate: '2024-01-01' },
        { seasonNumber: 2, name: 'Season 2', episodeCount: 8, airDate: '2025-01-01' },
      ],
    });
  });

  it('rejects mismatched TV identity and malformed season members', () => {
    const base = {
      ok: true,
      tmdbId: 42,
      title: 'The Show',
      seasons: [{ seasonNumber: 1, name: 'Season 1', episodeCount: 8, airDate: null }],
    };
    expect(() => mapTvSeasonCollection(base, 7)).toThrow(/Malformed TV seasons response/);
    expect(() =>
      mapTvSeasonCollection(
        { ...base, seasons: [...base.seasons, { ...base.seasons[0] }] },
        42,
      ),
    ).toThrow(/Malformed TV seasons response/);
    expect(() =>
      mapTvSeasonCollection(
        { ...base, seasons: [{ ...base.seasons[0], airDate: 'https://internal/private' }] },
        42,
      ),
    ).toThrow(/Malformed TV seasons response/);
  });

  it('strictly maps the extended request lifecycle response', () => {
    expect(
      mapMediaRequestAction({
        ok: true,
        partial_success: false,
        jellyseerr_request_id: 812,
        request_status: 'processing',
        already_requested: false,
        dashboard_state_persisted: true,
        reconciliation_queued: false,
        message: 'Request submitted to Jellyseerr.',
      }),
    ).toEqual({
      ok: true,
      partial_success: false,
      jellyseerr_request_id: 812,
      request_status: 'processing',
      already_requested: false,
      dashboard_state_persisted: true,
      reconciliation_queued: false,
      message: 'Request submitted to Jellyseerr.',
    });

    for (const malformed of [
      { ok: true },
      {
        ok: true,
        partial_success: false,
        jellyseerr_request_id: 0,
        request_status: 'processing',
        already_requested: false,
        dashboard_state_persisted: true,
        reconciliation_queued: false,
        message: 'Request submitted.',
      },
      {
        ok: true,
        partial_success: false,
        jellyseerr_request_id: 9,
        request_status: 'queued',
        already_requested: false,
        dashboard_state_persisted: true,
        reconciliation_queued: false,
        message: 'Request submitted.',
      },
    ]) {
      expect(() => mapMediaRequestAction(malformed)).toThrow(/Malformed media request response/);
    }

    expect(mapMediaRequestAction({ ok: false, error: 'This request is unavailable' })).toEqual({
      ok: false,
      error: 'This request is unavailable',
    });
  });
});
