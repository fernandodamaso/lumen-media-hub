import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { HttpMediaStackApi } from './http-media-stack-api';
import {
  mapLiveAutomationSummary,
  mapLiveJellyfinItem,
  mapLiveActivityFeed,
  mapLiveWatchNextItem,
  mapLiveRecentlyAvailableItem,
  mapLiveSystemResourcesDisk,
  mapLiveTorrent,
  requireHermesDiscoverPayload,
  requireExternalDiscoverPayload,
} from './live-api.mappers';

describe('live-api.mappers', () => {
  it('requires and validates library exclusion freshness for every Discover source', () => {
    for (const resource of ['Hermes', 'Jellyseerr', 'Trakt'] as const) {
      expect(() => {
        const payload: Record<string, unknown> = {
          items: [],
          library_exclusion: { status: 'stale', last_successful_refresh_at: '2026-08-11T12:00:00Z' },
          watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
        };
        if (resource === 'Hermes') requireHermesDiscoverPayload(payload);
        else requireExternalDiscoverPayload(payload, resource);
      }).not.toThrow();
    }
  });

  it('fails safe on malformed library status and timestamp', () => {
    expect(() => { requireExternalDiscoverPayload({
      items: [],
      library_exclusion: { status: 'broken', last_successful_refresh_at: null },
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    }, 'Jellyseerr'); }).toThrow(/library_exclusion is invalid/);
    expect(() => { requireExternalDiscoverPayload({
      items: [],
      library_exclusion: { status: 'stale', last_successful_refresh_at: 42 },
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    }, 'Trakt'); }).toThrow(/library_exclusion timestamp is invalid/);
  });

  it('preserves only the safe reconnect code on action mappings', async () => {
    const { mapDiscoverAction } = await import('../discover/discover-format');
    expect(mapDiscoverAction({ ok: false, error: 'Trakt reconnect required', code: 'reconnect_required' })).toMatchObject({
      ok: false,
      code: 'reconnect_required',
    });
    expect(mapDiscoverAction({ ok: false, error: 'failed', code: 'token-secret' })).not.toHaveProperty('code');
  });
  it('accepts valid Trakt watched freshness statuses', () => {
    for (const status of ['fresh', 'stale', 'unavailable'] as const) {
      expect(() => {
        requireExternalDiscoverPayload(
          {
            items: [],
            library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
            watched_exclusion: {
              status,
              last_successful_refresh_at: status === 'unavailable' ? null : '2026-08-11T12:00:00Z',
            },
          },
          'Trakt',
        );
      },
      ).not.toThrow();
    }
  });

  it('rejects invalid Trakt watched freshness wire values', () => {
    expect(() => {
      requireExternalDiscoverPayload(
        { items: [], library_exclusion: { status: 'fresh', last_successful_refresh_at: null }, watched_exclusion: { status: 'broken', last_successful_refresh_at: null } },
        'Trakt',
      );
    },
    ).toThrow(/watched_exclusion is invalid/);
    expect(() => {
      requireExternalDiscoverPayload(
        { items: [], library_exclusion: { status: 'fresh', last_successful_refresh_at: null }, watched_exclusion: { status: 'stale', last_successful_refresh_at: 42 } },
        'Trakt',
      );
    },
    ).toThrow(/watched_exclusion timestamp is invalid/);
  });

  it('requires watched freshness on successful Trakt envelopes only', () => {
    expect(() => {
      requireExternalDiscoverPayload({ items: [], library_exclusion: { status: 'fresh', last_successful_refresh_at: null } }, 'Trakt');
    }).toThrow(
      /watched_exclusion is required/,
    );
    expect(() => {
      requireExternalDiscoverPayload({
        items: [],
        library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      }, 'Jellyseerr');
    }).toThrow(/watched_exclusion is required/);
  });

  it('requires library freshness on successful Hermes and Trakt envelopes', () => {
    for (const resource of ['Hermes', 'Trakt'] as const) {
      expect(() => {
        const payload: Record<string, unknown> = {
          items: [],
          watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
        };
        if (resource === 'Hermes') requireHermesDiscoverPayload(payload);
        else requireExternalDiscoverPayload(payload, resource);
      }).toThrow(/library_exclusion is required/);

      expect(() => {
        const payload: Record<string, unknown> = {
          items: [],
          library_exclusion: null,
          watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
        };
        if (resource === 'Hermes') requireHermesDiscoverPayload(payload);
        else requireExternalDiscoverPayload(payload, resource);
      }).toThrow(/library_exclusion is required/);
    }
  });

  it('requires watched freshness on enabled Jellyseerr envelopes', () => {
    expect(() => { requireExternalDiscoverPayload({ items: [], enabled: true }, 'Jellyseerr'); })
      .toThrow(/library_exclusion is required/);
    expect(() => {
      requireExternalDiscoverPayload({
        items: [],
        enabled: true,
        library_exclusion: null,
        watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      }, 'Jellyseerr');
    }).toThrow(/library_exclusion is required/);
    expect(() => { requireExternalDiscoverPayload({
      items: [],
      enabled: true,
      library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    }, 'Jellyseerr'); })
      .toThrow(/watched_exclusion is required/);
    expect(() => { requireExternalDiscoverPayload({
      items: [],
      enabled: true,
      library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      watched_exclusion: null,
    }, 'Jellyseerr'); })
      .toThrow(/watched_exclusion is required/);
    expect(() => { requireExternalDiscoverPayload({ items: [], enabled: false }, 'Jellyseerr'); }).not.toThrow();
  });

  it('maps qbt torrents with downloaded from amount_left', () => {
    expect(
      mapLiveTorrent({
        hash: 'abc',
        name: 'Film',
        state: 'downloading',
        progress: 0.5,
        size: 100,
        amount_left: 40,
        dlspeed: 10,
        upspeed: 2,
        eta: 30,
        category: 'Movies',
      }),
    ).toEqual({
      hash: 'abc',
      name: 'Film',
      state: 'downloading',
      progress: 0.5,
      size: 100,
      downloaded: 60,
      dlspeed: 10,
      upspeed: 2,
      eta: 30,
      category: 'Movies',
    });
  });

  it('rejects qbt torrents that lack required identity fields', () => {
    expect(() =>
      mapLiveTorrent({
        name: 'Film',
        state: 'downloading',
        progress: 0.5,
        size: 100,
        dlspeed: 10,
        upspeed: 2,
        eta: 30,
      }),
    ).toThrow(/missing hash/);
  });

  it('rejects qbt torrents that coerce null numerics into zeros', () => {
    expect(() =>
      mapLiveTorrent({
        hash: 'abc',
        name: 'Film',
        state: 'downloading',
        progress: null,
        size: 100,
        dlspeed: 10,
        upspeed: 2,
        eta: 30,
      }),
    ).toThrow(/missing progress/);
  });

  it('rejects qbt torrents with a non-string category', () => {
    expect(() =>
      mapLiveTorrent({
        hash: 'abc',
        name: 'Film',
        state: 'downloading',
        progress: 0.5,
        size: 100,
        dlspeed: 10,
        upspeed: 2,
        eta: 30,
        category: 12,
      }),
    ).toThrow(/invalid category/);
  });

  it('maps jellyfin items with artwork state', () => {
    expect(mapLiveJellyfinItem({ id: '1', name: 'Dune', year: 2021, image: '/img' }, 'movie')).toEqual({
      id: '1',
      title: 'Dune',
      kind: 'movie',
      year: 2021,
      posterUrl: '/img',
      artworkState: 'ok',
      playable: true,
      episodeCount: null,
      played: false,
    });
    expect(mapLiveJellyfinItem({ id: '2', name: 'Show', episodeCount: 12, played: true }, 'series')).toEqual({
      id: '2',
      title: 'Show',
      kind: 'series',
      year: undefined,
      posterUrl: undefined,
      artworkState: 'missing',
      playable: true,
      episodeCount: 12,
      played: true,
    });
  });

  it('maps nested automation summary into flat services/preview/problems', () => {
    const dto = mapLiveAutomationSummary({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      sonarr: {
        ok: true,
        missing: 2,
        monitored: 10,
        queued: 1,
        missingItems: [{ label: 'Show S01E01', airDate: 'Tonight' }],
        queueItems: [{ label: 'Stuck episode', warning: true, status: 'warning' }],
      },
      radarr: { ok: true, movies: 5, missing: 0, queued: 0 },
      prowlarr: {
        ok: true,
        indexers: 4,
        enabled: 3,
        disabled: [{ name: 'SlowIndex' }],
        cooldown: [{ name: 'CoolIndex', until: '2026-07-13T15:00:00Z' }],
      },
      bazarr: { ok: false, error: 'Connection refused', wantedEpisodes: 0, wantedMovies: 0 },
    });

    expect(dto.generatedAt).toBe('2026-07-13T12:00:00Z');
    expect(dto.services?.find((s) => s.id === 'sonarr')).toMatchObject({ status: 'degraded' });
    expect(dto.services?.find((s) => s.id === 'bazarr')).toMatchObject({
      status: 'down',
      detail: 'Connection refused',
    });
    expect(dto.preview?.[0]?.title).toBe('Stuck episode');
    expect(dto.problems?.some((p) => p.serviceId === 'bazarr')).toBe(true);
    expect(dto.problems?.some((p) => p.id.includes('disabled'))).toBe(true);
    const prowlarrDisabled = dto.problems?.find((p) => p.id === 'prowlarr-disabled');
    expect(prowlarrDisabled?.items).toEqual([{ title: 'SlowIndex', when: 'disabled', href: null, posterUrl: null }]);
    expect(prowlarrDisabled?.itemCount).toBe(1);
    const prowlarrCooldown = dto.problems?.find((p) => p.id === 'prowlarr-cooldown');
    expect(prowlarrCooldown?.items).toEqual([{ title: 'CoolIndex', when: '2026-07-13T15:00:00Z', href: null, posterUrl: null }]);
    expect(prowlarrCooldown?.itemCount).toBe(1);
    const sonarrMissing = dto.problems?.find((p) => p.id === 'sonarr-missing');
    expect(sonarrMissing?.items).toEqual([{ title: 'Show S01E01', when: 'Tonight', href: null, posterUrl: null }]);
    expect(sonarrMissing?.itemCount).toBe(2);
  });

  it('does not invent a Bazarr outage when the optional block is absent', () => {
    const dto = mapLiveAutomationSummary({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      sonarr: { ok: true, missing: 0, monitored: 1, queued: 0 },
      radarr: { ok: true, movies: 1, missing: 0, queued: 0 },
      prowlarr: { ok: true, indexers: 1, enabled: 1 },
    });

    expect(dto.services?.some((service) => service.id === 'bazarr')).toBe(false);
    expect(dto.problems?.some((problem) => problem.serviceId === 'bazarr')).toBe(false);
  });

  it('passes through posterUrl on problem detail items and normalizes blank/null/undefined to null', () => {
    const dto = mapLiveAutomationSummary({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      sonarr: {
        ok: true,
        missing: 2,
        monitored: 10,
        queued: 1,
        missingItems: [
          { label: 'With Poster', airDate: 'Tonight', posterUrl: 'http://localhost:8989/MediaCover/13/poster-250.jpg' },
          { label: 'No Poster', airDate: 'Tomorrow' },
          { label: 'Blank Poster', airDate: 'Later', posterUrl: '' },
          { label: 'Whitespace Poster', airDate: 'Soon', posterUrl: '   ' },
        ],
      },
      radarr: { ok: true, movies: 5, missing: 0, queued: 0 },
    });
    const sonarrMissing = dto.problems?.find((p) => p.id === 'sonarr-missing');
    expect(sonarrMissing?.items).toEqual([
      { title: 'With Poster', when: 'Tonight', href: null, posterUrl: 'http://localhost:8989/MediaCover/13/poster-250.jpg' },
      { title: 'No Poster', when: 'Tomorrow', href: null, posterUrl: null },
      { title: 'Blank Poster', when: 'Later', href: null, posterUrl: null },
      { title: 'Whitespace Poster', when: 'Soon', href: null, posterUrl: null },
    ]);
  });

  it('passes through backend href on problem detail items and maps missing/blank to null', () => {
    const dto = mapLiveAutomationSummary({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      sonarr: {
        ok: true,
        missing: 2,
        monitored: 10,
        queued: 1,
        missingItems: [
          { label: 'With Link', airDate: 'Tonight', href: 'http://sonarr/series/1' },
          { label: 'No Link', airDate: 'Tomorrow' },
          { label: 'Blank Link', airDate: 'Later', href: '' },
        ],
      },
      radarr: { ok: true, movies: 5, missing: 0, queued: 0 },
    });
    const sonarrMissing = dto.problems?.find((p) => p.id === 'sonarr-missing');
    expect(sonarrMissing?.items).toEqual([
      { title: 'With Link', when: 'Tonight', href: 'http://sonarr/series/1', posterUrl: null },
      { title: 'No Link', when: 'Tomorrow', href: null, posterUrl: null },
      { title: 'Blank Link', when: 'Later', href: null, posterUrl: null },
    ]);
  });

  it('rejects a failed automation envelope with no service blocks', () => {
    expect(() => mapLiveAutomationSummary({ ok: false, error: 'backend down' })).toThrow('backend down');
  });

  it('passes through service latencyMs when present', () => {
    const dto = mapLiveAutomationSummary({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      sonarr: { ok: true, missing: 0, monitored: 1, queued: 0, latencyMs: 21 },
      radarr: { ok: true, movies: 1, missing: 0, queued: 0 },
    });
    expect(dto.services?.find((s) => s.id === 'sonarr')?.latencyMs).toBe(21);
    expect(dto.services?.find((s) => s.id === 'radarr')?.latencyMs).toBeNull();
  });

  it('maps live storage volume from system resources disk', () => {
    expect(
      mapLiveSystemResourcesDisk({ path: '/data', total: 100, used: 30, free: 70, percent: 30 }),
    ).toEqual({ id: 'media-volume', label: 'Media volume (/data)', kind: 'library', usedBytes: 30, totalBytes: 100 });
    expect(mapLiveSystemResourcesDisk({ path: '/data', used: 5, total: 50 })).toEqual({
      id: 'media-volume',
      label: 'Media volume (/data)',
      kind: 'library',
      usedBytes: 5,
      totalBytes: 50,
    });
    expect(mapLiveSystemResourcesDisk({ path: '/data', used: 0, total: 0 })).toEqual({
      id: 'media-volume',
      label: 'Media volume (/data)',
      kind: 'library',
      usedBytes: 0,
      totalBytes: 0,
    });
  });

  it('rejects system resources disk that lack required fields', () => {
    expect(() => mapLiveSystemResourcesDisk({ total: 20, used: 10 })).toThrow(/missing disk.path/);
    expect(() => mapLiveSystemResourcesDisk({ path: '/data', total: 20 })).toThrow(/missing disk.used/);
    expect(() => mapLiveSystemResourcesDisk({ path: '/data', used: 10 })).toThrow(/missing disk.total/);
  });

  it('rejects system resources disk with used exceeding total', () => {
    expect(() =>
      mapLiveSystemResourcesDisk({ path: '/data', total: 100, used: 150 }),
    ).toThrow(/used exceeds/);
  });

  it('rejects system resources disk with negative capacities', () => {
    expect(() =>
      mapLiveSystemResourcesDisk({ path: '/data', total: 100, used: -1 }),
    ).toThrow(/negative disk capacity/);
  });

  it('rejects jellyfin items that lack required identity', () => {
    expect(() => mapLiveJellyfinItem({ name: 'Dune' }, 'movie')).toThrow(/missing id/);
    expect(() => mapLiveJellyfinItem({ id: '1' }, 'movie')).toThrow(/missing name/);
  });

  it('maps watch-next items and rejects malformed progress or parent identity', () => {
    expect(
      mapLiveWatchNextItem({
        id: 'ep-1',
        parentId: 'series-1',
        title: 'The Expanse',
        subtitle: 'S04E02 · Jetsam',
        kind: 'episode',
        image: '/img',
        progressPercent: 42,
      }),
    ).toMatchObject({
      id: 'ep-1',
      parentId: 'series-1',
      title: 'The Expanse',
      kind: 'episode',
      progressPercent: 42,
      posterUrl: '/img',
    });

    expect(() =>
      mapLiveWatchNextItem({
        id: 'mv-1',
        parentId: 'series-1',
        title: 'Dune',
        subtitle: '',
        kind: 'movie',
        progressPercent: 10,
      }),
    ).toThrow(/movie parentId must be null/);

    expect(() =>
      mapLiveWatchNextItem({
        id: 'ep-1',
        parentId: 'series-1',
        title: 'Show',
        subtitle: '',
        kind: 'episode',
        progressPercent: Number.NaN,
      }),
    ).toThrow(/missing progressPercent/);
  });

  it('maps recently-available items and rejects malformed timestamps and parent identity', () => {
    expect(
      mapLiveRecentlyAvailableItem({
        id: 'ep-1',
        parentId: 'series-1',
        title: 'Saga of Tanya the Evil',
        subtitle: 'S02E05 · Lamb',
        kind: 'episode',
        image: '/img',
        thumbUrl: '/thumb',
        availableAt: '2026-08-11T12:14:33Z',
        playable: true,
        year: 2026,
      }),
    ).toMatchObject({
      id: 'ep-1',
      parentId: 'series-1',
      kind: 'episode',
      availableAt: '2026-08-11T12:14:33Z',
      playable: true,
      posterUrl: '/img',
      thumbUrl: '/thumb',
    });

    expect(() =>
      mapLiveRecentlyAvailableItem({
        id: 'mv-1',
        parentId: 'series-1',
        title: 'Mickey 17',
        subtitle: '',
        kind: 'movie',
        availableAt: '2026-08-11T12:14:33Z',
        playable: true,
      }),
    ).toThrow(/movie parentId must be null/);

    expect(() =>
      mapLiveRecentlyAvailableItem({
        id: 'ep-1',
        parentId: 'series-1',
        title: 'Show',
        subtitle: 'S01E01',
        kind: 'episode',
        availableAt: '2026-08-11T12:14:33',
        playable: true,
      }),
    ).toThrow(/availableAt/);

    expect(() =>
      mapLiveRecentlyAvailableItem({
        id: 'ep-1',
        parentId: 'series-1',
        title: 'Show',
        subtitle: 'S01E01',
        kind: 'episode',
        availableAt: '2026-08-11T12:14:33Z',
        playable: false,
      }),
    ).toThrow(/not playable/);

    expect(() =>
      mapLiveRecentlyAvailableItem({
        id: 'ep-1',
        parentId: 'series-1',
        title: 'Show',
        subtitle: '',
        kind: 'episode',
        availableAt: '2026-08-11T12:14:33Z',
        playable: true,
      }),
    ).toThrow(/missing subtitle/);
  });

  it('maps watch-next metadata and defaults missing fields to null', () => {
    const rich = mapLiveWatchNextItem({
      id: 'ep-1',
      parentId: 'series-1',
      title: 'The Expanse',
      subtitle: 'S04E02 · Jetsam',
      kind: 'episode',
      progressPercent: 42,
      year: 2015,
      rating: 8.3,
      genres: ['Sci-Fi', 'Adventure'],
      overview: 'Politics and survival.',
      runtimeTicks: 3_600_000_000,
      positionTicks: 1_500_000_000,
      backdropUrl: 'http://jellyfin/Items/series-1/Images/Backdrop',
      thumbUrl: 'http://jellyfin/Items/series-1/Images/Thumb',
    });
    expect(rich).toMatchObject({
      year: 2015,
      rating: 8.3,
      genres: ['Sci-Fi', 'Adventure'],
      overview: 'Politics and survival.',
      runtimeTicks: 3_600_000_000,
      positionTicks: 1_500_000_000,
      backdropUrl: 'http://jellyfin/Items/series-1/Images/Backdrop',
      thumbUrl: 'http://jellyfin/Items/series-1/Images/Thumb',
    });

    const sparse = mapLiveWatchNextItem({
      id: 'mv-1',
      parentId: null,
      title: 'Dune',
      subtitle: '',
      kind: 'movie',
      progressPercent: 18,
    });
    expect(sparse).toMatchObject({
      year: null,
      rating: null,
      genres: [],
      overview: null,
      runtimeTicks: null,
      positionTicks: null,
      backdropUrl: null,
      thumbUrl: null,
    });

    expect(() =>
      mapLiveWatchNextItem({
        id: 'mv-2',
        parentId: null,
        title: 'Dune',
        subtitle: '',
        kind: 'movie',
        progressPercent: 18,
        genres: ['Drama', 7],
      }),
    ).toThrow(/invalid genres/);
  });

  it('maps queue-only Sonarr degradation into queue problems when nothing is missing', () => {
    const dto = mapLiveAutomationSummary({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      sonarr: {
        ok: true,
        missing: 0,
        monitored: 10,
        queued: 1,
        queueItems: [{ label: 'Stuck episode', warning: true, status: 'warning' }],
      },
      radarr: { ok: true, movies: 5, missing: 0, queued: 0 },
    });

    expect(dto.services?.find((s) => s.id === 'sonarr')?.status).toBe('degraded');
    expect(dto.problems?.find((p) => p.id === 'sonarr-missing')).toBeUndefined();
    expect(dto.problems?.find((p) => p.id === 'sonarr-queue')).toMatchObject({
      serviceId: 'sonarr',
      items: [{ title: 'Stuck episode', when: 'warning', href: null, posterUrl: null }],
    });
  });

  it('maps automation ok:false when nested service blocks remain', () => {
    const dto = mapLiveAutomationSummary({
      ok: false,
      error: 'partial outage',
      generatedAt: '2026-07-13T12:00:00Z',
      sonarr: { ok: true, missing: 0, monitored: 2, queued: 0 },
      radarr: { ok: false, error: 'timeout' },
    });
    expect(dto.services?.find((s) => s.id === 'sonarr')?.status).toBe('healthy');
    expect(dto.services?.find((s) => s.id === 'radarr')?.status).toBe('down');
    expect(dto.problems?.some((p) => p.summary === 'partial outage')).toBe(true);
  });

  it('rejects automation summaries that invent freshness instead of using backend generatedAt', () => {
    const missing = mapLiveAutomationSummary({
      ok: true,
      sonarr: { ok: true, missing: 0, monitored: 1, queued: 0 },
    });
    expect(missing.generatedAt).toBe('');

    expect(() =>
      mapLiveAutomationSummary({
        ok: true,
        generatedAt: 'not-a-date',
        sonarr: { ok: true, missing: 0, monitored: 1, queued: 0 },
      }),
    ).toThrow(/invalid generatedAt/);
  });

  it('maps activity feeds and rejects malformed members', () => {
    const feed = mapLiveActivityFeed({
      ok: true,
      generatedAt: '2026-07-30T00:20:00Z',
      sources: { sonarr: 'ok', radarr: 'error' },
      items: [
        {
          id: 'sonarr:48211',
          source: 'sonarr',
          kind: 'grabbed',
          title: 'The Shōgun Court',
          subtitle: 'S01E07 · 1080p WEB-DL',
          timestamp: '2026-07-30T00:18:41Z',
          href: 'http://localhost:8989/series/the-shogun-court',
        },
      ],
    });
    expect(feed).toEqual({
      ok: true,
      generatedAt: '2026-07-30T00:20:00Z',
      sources: { sonarr: 'ok', radarr: 'error' },
      items: [
        {
          id: 'sonarr:48211',
          source: 'sonarr',
          kind: 'grabbed',
          title: 'The Shōgun Court',
          subtitle: 'S01E07 · 1080p WEB-DL',
          timestamp: '2026-07-30T00:18:41Z',
          href: 'http://localhost:8989/series/the-shogun-court',
        },
      ],
    });

    expect(() =>
      mapLiveActivityFeed({
        ok: true,
        sources: { sonarr: 'ok', radarr: 'ok' },
        items: [{ id: 'sonarr:1', source: 'sonarr', kind: 'mystery', title: 'Show', timestamp: '2026-07-30T00:18:41Z' }],
      }),
    ).toThrow(/invalid kind/);

    expect(() =>
      mapLiveActivityFeed({
        ok: true,
        sources: { sonarr: 'ok', radarr: 'ok' },
        items: [{ id: 'sonarr:1', source: 'prowlarr', kind: 'grabbed', title: 'Show', timestamp: '2026-07-30T00:18:41Z' }],
      }),
    ).toThrow(/invalid source/);
  });
});

describe('HttpMediaStackApi', () => {
  let api: HttpMediaStackApi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), HttpMediaStackApi],
    });
    api = TestBed.inject(HttpMediaStackApi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  function flushSidebarProbes(options?: { jellyfinOk?: boolean; qbitOk?: boolean }): void {
    const jellyfinOk = options?.jellyfinOk !== false;
    const qbitOk = options?.qbitOk !== false;
    const jellyfin = http.expectOne('/api/jellyfin/series');
    if (jellyfinOk) {
      jellyfin.flush({ ok: true, items: [] });
    } else {
      jellyfin.flush({ error: 'jellyfin down' }, { status: 503, statusText: 'Unavailable' });
    }
    const qbit = http.expectOne('/api/qbt/torrents');
    if (qbitOk) {
      qbit.flush([]);
    } else {
      qbit.flush({ error: 'qbit down' }, { status: 503, statusText: 'Unavailable' });
    }
  }

  function flushAutomationSummary(
    body: object,
    probeOptions?: { jellyfinOk?: boolean; qbitOk?: boolean },
  ): void {
    // Summary + sidebar probes are requested in parallel.
    http.expectOne('/api/automation/summary').flush(body);
    flushSidebarProbes(probeOptions);
  }

  it('GETs torrents and maps payloads', async () => {
    const pending = api.listTorrents();
    const req = http.expectOne('/api/qbt/torrents');
    expect(req.request.method).toBe('GET');
    req.flush([
      {
        hash: 'h1',
        name: 'A',
        state: 'downloading',
        progress: 0.25,
        size: 400,
        amount_left: 300,
        dlspeed: 1,
        upspeed: 0,
        eta: 10,
      },
    ]);
    await expect(pending).resolves.toEqual([
      expect.objectContaining({ id: 'h1', downloaded: 100, progress: 25 }),
    ]);
  });

  it('cancels the torrents HTTP request when the abort signal fires', async () => {
    const abort = new AbortController();
    const pending = api.listTorrents(abort.signal);
    const req = http.expectOne('/api/qbt/torrents');
    expect(req.request.method).toBe('GET');

    abort.abort();
    expect(req.cancelled).toBe(true);
    await expect(pending).rejects.toBeTruthy();
  });

  it('accepts a valid empty torrent list', async () => {
    const pending = api.listTorrents();
    http.expectOne('/api/qbt/torrents').flush([]);
    await expect(pending).resolves.toEqual([]);
  });

  it('accepts a successful envelope with a torrents array', async () => {
    const pending = api.listTorrents();
    http.expectOne('/api/qbt/torrents').flush({
      ok: true,
      torrents: [
        {
          hash: 'h2',
          name: 'B',
          state: 'paused',
          progress: 1,
          size: 100,
          amount_left: 0,
          dlspeed: 0,
          upspeed: 0,
          eta: 0,
        },
      ],
    });
    await expect(pending).resolves.toEqual([
      expect.objectContaining({ id: 'h2', name: 'B', progress: 100 }),
    ]);
  });

  it('rejects torrents when envelope ok is false', async () => {
    const pending = api.listTorrents();
    http.expectOne('/api/qbt/torrents').flush({ ok: false, error: 'qbt down' });
    await expect(pending).rejects.toThrow('qbt down');
  });

  it('rejects null torrent payloads', async () => {
    const pending = api.listTorrents();
    http.expectOne('/api/qbt/torrents').flush(null);
    await expect(pending).rejects.toThrow(/Malformed/);
  });

  it('rejects torrent members missing required fields before mapping', async () => {
    const cases: Array<{ label: string; body: object[] }> = [
      {
        label: 'missing hash',
        body: [
          {
            name: 'A',
            state: 'downloading',
            progress: 0.5,
            size: 100,
            dlspeed: 1,
            upspeed: 0,
            eta: 10,
          },
        ],
      },
      {
        label: 'missing name',
        body: [
          {
            hash: 'h1',
            state: 'downloading',
            progress: 0.5,
            size: 100,
            dlspeed: 1,
            upspeed: 0,
            eta: 10,
          },
        ],
      },
      {
        label: 'missing progress',
        body: [
          {
            hash: 'h1',
            name: 'A',
            state: 'downloading',
            size: 100,
            dlspeed: 1,
            upspeed: 0,
            eta: 10,
          },
        ],
      },
      {
        label: 'null progress',
        body: [
          {
            hash: 'h1',
            name: 'A',
            state: 'downloading',
            progress: null,
            size: 100,
            dlspeed: 1,
            upspeed: 0,
            eta: 10,
          },
        ],
      },
    ];

    for (const testCase of cases) {
      const pending = api.listTorrents();
      http.expectOne('/api/qbt/torrents').flush(testCase.body);
      await expect(pending, testCase.label).rejects.toThrow(/Malformed torrents response/);
    }
  });

  it('rejects the whole list when one torrent member is malformed', async () => {
    const pending = api.listTorrents();
    http.expectOne('/api/qbt/torrents').flush([
      {
        hash: 'good',
        name: 'Good',
        state: 'downloading',
        progress: 0.5,
        size: 100,
        amount_left: 50,
        dlspeed: 1,
        upspeed: 0,
        eta: 10,
      },
      {
        hash: '',
        name: 'Bad',
        state: 'downloading',
        progress: 0.1,
        size: 50,
        dlspeed: 0,
        upspeed: 0,
        eta: 0,
      },
    ]);
    await expect(pending).rejects.toThrow(/member 1 is missing hash/);
  });

  it('POSTs pause and resume actions', async () => {
    const pause = api.pauseAll();
    const pauseReq = http.expectOne('/api/stop-all');
    expect(pauseReq.request.method).toBe('POST');
    pauseReq.flush({ ok: true });
    await expect(pause).resolves.toBeUndefined();

    const resume = api.resumeAll();
    const resumeReq = http.expectOne('/api/start-all');
    expect(resumeReq.request.method).toBe('POST');
    resumeReq.flush({ ok: true });
    await expect(resume).resolves.toBeUndefined();
  });

  it('POSTs per-torrent stop and start with the torrent id', async () => {
    const pause = api.pauseTorrent('abc123');
    const pauseReq = http.expectOne('/api/qbt/torrents/stop');
    expect(pauseReq.request.method).toBe('POST');
    expect(pauseReq.request.body).toEqual({ id: 'abc123' });
    pauseReq.flush({ ok: true });
    await expect(pause).resolves.toBeUndefined();

    const resume = api.resumeTorrent('abc123');
    const resumeReq = http.expectOne('/api/qbt/torrents/start');
    expect(resumeReq.request.method).toBe('POST');
    expect(resumeReq.request.body).toEqual({ id: 'abc123' });
    resumeReq.flush({ ok: true });
    await expect(resume).resolves.toBeUndefined();

    const failed = api.pauseTorrent('abc123');
    http.expectOne('/api/qbt/torrents/stop').flush({ ok: false, error: 'qbt locked' });
    await expect(failed).rejects.toThrow('qbt locked');
  });

  it('GETs system resources and maps disk to storage volume', async () => {
    const pending = api.getStorageOverview();
    http.expectOne('/api/system/resources').flush({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      disk: { path: '/data', total: 100, used: 30, free: 70, percent: 30 },
    });
    await expect(pending).resolves.toEqual({
      generatedAt: '2026-07-13T12:00:00Z',
      volumes: [
        { id: 'media-volume', label: 'Media volume (/data)', kind: 'library', usedBytes: 30, totalBytes: 100 },
      ],
    });
  });

  it('rejects malformed system resources responses', async () => {
    const missingDisk = api.getStorageOverview();
    http.expectOne('/api/system/resources').flush({ ok: true, generatedAt: '2026-07-13T12:00:00Z' });
    await expect(missingDisk).rejects.toThrow(/missing disk/);

    const nullDisk = api.getStorageOverview();
    http.expectOne('/api/system/resources').flush({ ok: true, disk: null });
    await expect(nullDisk).rejects.toThrow(/missing disk/);

    const missingPath = api.getStorageOverview();
    http.expectOne('/api/system/resources').flush({
      ok: true,
      disk: { total: 100, used: 30, free: 70, percent: 30 },
    });
    await expect(missingPath).rejects.toThrow(/missing disk.path/);

    const withoutOptionalFields = api.getStorageOverview();
    http.expectOne('/api/system/resources').flush({
      ok: true,
      disk: { path: '/data', total: 100, used: 30 },
    });
    await expect(withoutOptionalFields).resolves.toEqual(
      expect.objectContaining({
        volumes: [{ id: 'media-volume', label: 'Media volume (/data)', kind: 'library', usedBytes: 30, totalBytes: 100 }],
      }),
    );

    const usedExceeds = api.getStorageOverview();
    http.expectOne('/api/system/resources').flush({
      ok: true,
      disk: { path: '/data', total: 100, used: 150 },
    });
    await expect(usedExceeds).rejects.toThrow(/used exceeds/);
  });

  it('GETs jellyfin movies and series concurrently for library stats', async () => {
    const pending = api.getLibraryStats();
    const movieReq = http.expectOne('/api/jellyfin/movies');
    const seriesReq = http.expectOne('/api/jellyfin/series');
    movieReq.flush({ ok: true, items: [{ id: 'm1', name: 'Movie 1' }, { id: 'm2', name: 'Movie 2' }] });
    seriesReq.flush({ ok: true, items: [{ id: 's1', name: 'Series 1' }] });
    await expect(pending).resolves.toEqual({ movies: 2, series: 1, availability: 'complete' });

    const zeros = api.getLibraryStats();
    http.expectOne('/api/jellyfin/movies').flush({ ok: true, items: [] });
    http.expectOne('/api/jellyfin/series').flush({ ok: true, items: [] });
    await expect(zeros).resolves.toEqual({ movies: 0, series: 0, availability: 'complete' });
  });

  it('prefers jellyfin list total over mapped item length for library stats', async () => {
    const pending = api.getLibraryStats();
    http.expectOne('/api/jellyfin/movies').flush({
      ok: true,
      total: 428,
      items: [{ id: 'm1', name: 'Movie 1' }],
    });
    http.expectOne('/api/jellyfin/series').flush({
      ok: true,
      total: 76,
      items: [],
    });
    await expect(pending).resolves.toEqual({ movies: 428, series: 76, availability: 'complete' });
  });

  it('falls back to mapped jellyfin counts when total is absent or invalid', async () => {
    const pending = api.getLibraryStats();
    http.expectOne('/api/jellyfin/movies').flush({
      ok: true,
      items: [
        { id: 'm1', name: 'Movie 1' },
        { id: 'm2', name: 'Movie 2' },
      ],
    });
    http.expectOne('/api/jellyfin/series').flush({
      ok: true,
      total: -1,
      items: [{ id: 's1', name: 'Series 1' }],
    });
    await expect(pending).resolves.toEqual({ movies: 2, series: 1, availability: 'complete' });
  });

  it('rejects jellyfin stats fallback when blank items cannot be mapped', async () => {
    // Raw `items.length` would return 3; mapping matches listLibraryItems and fails closed.
    const pending = api.getLibraryStats();
    http.expectOne('/api/jellyfin/movies').flush({
      ok: true,
      items: [
        { id: 'm1', name: 'Movie 1' },
        { id: 'blank', name: '   ' },
        { id: 'm2', name: 'Movie 2' },
      ],
    });
    http.expectOne('/api/jellyfin/series').flush({ ok: true, items: [] });
    await expect(pending).rejects.toThrow(/missing name/);
  });

  it('dedupes concurrent identical GETs into one HTTP request', async () => {
    const first = api.listLibraryItems({ kind: 'movie' });
    const second = api.listLibraryItems({ kind: 'movie' });
    const req = http.expectOne('/api/jellyfin/movies');
    req.flush({ ok: true, items: [{ id: 'm1', name: 'Movie 1' }] });
    http.expectNone('/api/jellyfin/movies');
    const [a, b] = await Promise.all([first, second]);
    expect(a.items).toHaveLength(1);
    expect(b.items).toHaveLength(1);
  });

  it('rejects library stats when movies request fails', async () => {
    const pending = api.getLibraryStats();
    http.expectOne('/api/jellyfin/movies').flush({ ok: false, error: 'movies offline' });
    await expect(pending).rejects.toThrow('movies offline');
    http.expectOne('/api/jellyfin/series').flush({ ok: true, items: [] });
  });

  it('rejects library stats when series request fails', async () => {
    const pending = api.getLibraryStats();
    const movieReq = http.expectOne('/api/jellyfin/movies');
    http.expectOne('/api/jellyfin/series').flush({ error: 'series boom' }, { status: 500, statusText: 'Err' });
    await expect(pending).rejects.toThrow('series boom');
    movieReq.flush({ ok: true, items: [] });
  });

  it('fail-fast: rejects immediately when the first jellyfin request fails', async () => {
    const pending = api.getLibraryStats();
    http.expectOne('/api/jellyfin/movies').flush({ ok: false, error: 'movies offline' });
    // Assert rejection without flushing the /jellyfin/series request — Promise.all rejects
    // as soon as any member rejects, it does not wait for remaining requests.
    await expect(pending).rejects.toThrow('movies offline');
    http.expectOne('/api/jellyfin/series').flush({ ok: true, items: [] });
  });

  it('unwraps calendar envelope and rejects ok:false or malformed members', async () => {
    const pending = api.listCalendarEvents();
    http.expectOne('/api/sonarr/calendar').flush({
      ok: true,
      events: [{ title: 'Show', additional: 'S01E01', date: '20:00', airDate: '2026-07-13' }],
    });
    await expect(pending).resolves.toEqual([
      expect.objectContaining({ title: 'Show', subtitle: 'S01E01' }),
    ]);

    const failed = api.listCalendarEvents();
    http.expectOne('/api/sonarr/calendar').flush({ ok: false, error: 'sonarr offline' });
    await expect(failed).rejects.toThrow('sonarr offline');

    const malformed = api.listCalendarEvents();
    http.expectOne('/api/sonarr/calendar').flush({
      ok: true,
      events: [{ additional: 'S01E01', date: '20:00' }],
    });
    await expect(malformed).rejects.toThrow(/missing title/);
  });

  it('GETs arr library and cron logs', async () => {
    const library = api.getArrLibrary();
    http.expectOne('/api/arr/library').flush({ ok: true, series: { show: 'slug' }, movies: {} });
    await expect(library).resolves.toMatchObject({ ok: true, series: { show: 'slug' } });

    const logs = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({ ok: true, generatedAt: '2026-07-13T12:00:00Z', logs: [] });
    await expect(logs).resolves.toMatchObject({ ok: true, currentRuns: [], generatedAt: '2026-07-13T12:00:00Z' });
  });

  it('merges jellyfin movies and series for listLibraryItems', async () => {
    const pending = api.listLibraryItems();
    const movieReq = http.expectOne('/api/jellyfin/movies');
    const seriesReq = http.expectOne('/api/jellyfin/series');
    movieReq.flush({ ok: true, items: [{ id: 'm1', name: 'Movie', year: 2020, image: '/m' }] });
    seriesReq.flush({ ok: true, items: [{ id: 's1', name: 'Series' }] });
    await expect(pending).resolves.toEqual({
      availability: 'complete',
      movieCount: 1,
      seriesCount: 1,
      items: [
        expect.objectContaining({ id: 'm1', kind: 'movie', title: 'Movie' }),
        expect.objectContaining({ id: 's1', kind: 'series', title: 'Series', artworkState: 'missing' }),
      ],
    });
  });

  it('carries jellyfin list totals when larger than returned items', async () => {
    const pending = api.listLibraryItems();
    http.expectOne('/api/jellyfin/movies').flush({
      ok: true,
      total: 428,
      items: [{ id: 'm1', name: 'Movie', year: 2020, image: '/m' }],
    });
    http.expectOne('/api/jellyfin/series').flush({
      ok: true,
      total: 76,
      items: [{ id: 's1', name: 'Series' }],
    });
    await expect(pending).resolves.toMatchObject({
      availability: 'complete',
      movieCount: 428,
      seriesCount: 76,
      items: [expect.objectContaining({ id: 'm1' }), expect.objectContaining({ id: 's1' })],
    });
  });

  it('filters jellyfin requests by kind', async () => {
    const moviesOnly = api.listLibraryItems({ kind: 'movie' });
    http.expectOne('/api/jellyfin/movies').flush({ ok: true, items: [{ id: 'm1', name: 'Movie' }] });
    http.expectNone('/api/jellyfin/series');
    await expect(moviesOnly).resolves.toMatchObject({
      availability: 'complete',
      items: [{ id: 'm1' }],
      movieCount: 1,
      seriesCount: 0,
    });

    const seriesOnly = api.listLibraryItems({ kind: 'series' });
    http.expectOne('/api/jellyfin/series').flush({ ok: true, items: [{ id: 's1', name: 'Series' }] });
    http.expectNone('/api/jellyfin/movies');
    await expect(seriesOnly).resolves.toMatchObject({
      availability: 'complete',
      items: [{ id: 's1' }],
      movieCount: 0,
      seriesCount: 1,
    });
  });

  it('rejects filtered jellyfin loads when the requested kind fails', async () => {
    const moviesOnly = api.listLibraryItems({ kind: 'movie' });
    http.expectOne('/api/jellyfin/movies').flush({ ok: false, error: 'movies down' });
    http.expectNone('/api/jellyfin/series');
    await expect(moviesOnly).rejects.toThrow('movies down');

    const seriesOnly = api.listLibraryItems({ kind: 'series' });
    http.expectOne('/api/jellyfin/series').flush({ ok: false, error: 'series down' });
    http.expectNone('/api/jellyfin/movies');
    await expect(seriesOnly).rejects.toThrow('series down');
  });

  it('maps automation summary from nested live payload and probes sidebar services', async () => {
    const pending = api.getAutomationSummary();
    flushAutomationSummary({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      sonarr: { ok: true, missing: 0, monitored: 1, queued: 0 },
      radarr: { ok: true, movies: 1, missing: 0, queued: 0 },
      prowlarr: { ok: true, indexers: 1, enabled: 1 },
      bazarr: { ok: true, wantedEpisodes: 0, wantedMovies: 0 },
    });
    const summary = await pending;
    expect(summary.generatedAt).toBe('2026-07-13T12:00:00Z');
    expect(summary.services).toHaveLength(6);
    expect(summary.services.find((s) => s.id === 'jellyfin')).toMatchObject({ status: 'healthy' });
    expect(summary.services.find((s) => s.id === 'qbittorrent')).toMatchObject({ status: 'healthy' });
    expect(summary.services.filter((s) => ['sonarr', 'radarr', 'prowlarr', 'bazarr'].includes(s.id)).every((s) => s.status === 'healthy')).toBe(true);
  });

  it('keeps discover feedback PATCH separate from requestMedia POST', async () => {
    const feedback = api.submitHermesFeedback('rec-1', 'liked', { notes: 'great' });
    const feedbackReq = http.expectOne('/api/discover/hermes/rec-1');
    expect(feedbackReq.request.method).toBe('PATCH');
    expect(feedbackReq.request.body).toEqual({ status: 'liked', notes: 'great' });
    feedbackReq.flush({ ok: true });
    await expect(feedback).resolves.toMatchObject({ ok: true });

    const request = api.requestMedia({ mediaType: 'movie', mediaId: 42, hermesId: 'rec-1' });
    const requestReq = http.expectOne('/api/discover/request');
    expect(requestReq.request.method).toBe('POST');
    expect(requestReq.request.body).toEqual({ mediaType: 'movie', mediaId: 42, hermesId: 'rec-1' });
    requestReq.flush({ ok: true, jellyseerr_request_id: 9 });
    await expect(request).resolves.toMatchObject({ ok: true, jellyseerr_request_id: 9 });
  });

  it('posts queue hygiene mode and strictly maps the run result', async () => {
    const pending = api.runQueueHygiene('observe');
    const request = http.expectOne('/api/automation/queue-hygiene/run');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ mode: 'observe' });
    request.flush({
      ok: true,
      status: 'observed',
      mode: 'observe',
      circuitOpen: false,
      eligibleCount: 0,
      blockedCount: 0,
      eligibleItems: [],
      blockedItems: [],
      lastCycleAt: '2026-08-23T12:00:00Z',
      lastCleanup: null,
      verification: null,
      counts: { eligible: 0, blocked: 0, queued: 0 },
    });
    await expect(pending).resolves.toMatchObject({ status: 'observed', mode: 'observe' });
  });

  it('rejects malformed queue hygiene run results', async () => {
    const pending = api.runQueueHygiene('auto');
    const request = http.expectOne('/api/automation/queue-hygiene/run');
    request.flush({ ok: true, status: 'cleaned', mode: 'auto', circuitOpen: false });
    await expect(pending).rejects.toThrow('Malformed queue-hygiene run response');
  });

  it('maps queue hygiene diagnostics and degrades reachable Sonarr', () => {
    const dto = mapLiveAutomationSummary({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      sonarr: {
        ok: true,
        degraded: true,
        missing: 0,
        monitored: 1,
        queued: 0,
        queueHygiene: {
          mode: 'observe',
          circuitOpen: false,
          eligibleCount: 1,
          blockedCount: 0,
          eligibleItems: [{
            downloadId: 'a'.repeat(40),
            queueIds: [101],
            titles: ['Demo Show S01E02'],
            reason: 'Not an upgrade for existing episode file(s).',
            completedAt: '2026-07-13T08:00:00Z',
            ageHours: 4,
          }],
          blockedItems: [],
          lastCycleAt: '2026-07-13T12:00:00Z',
          lastCleanup: null,
          verification: null,
        },
      },
    });
    expect(dto.queueHygiene?.eligibleCount).toBe(1);
    expect(dto.services?.find((service) => service.id === 'sonarr')).toMatchObject({ status: 'degraded' });
    expect(dto.problems?.find((problem) => problem.id === 'sonarr-queue-hygiene')).toMatchObject({ itemCount: 1 });
  });

  it('maps HTTP 400 confirmation_required to a soft discover action', async () => {
    const feedback = api.submitHermesFeedback('rec-tv', 'watched');
    const feedbackReq = http.expectOne('/api/discover/hermes/rec-tv');
    feedbackReq.flush(
      { ok: false, code: 'confirmation_required', error: 'Confirmation required' },
      { status: 400, statusText: 'Bad Request' },
    );
    await expect(feedback).resolves.toMatchObject({
      ok: false,
      code: 'confirmation_required',
    });
  });

  it('loads discover sources and request-more', async () => {
    const hermes = api.listHermesRecommendations();
    http.expectOne('/api/discover/hermes').flush({
      ok: true,
      items: [],
      library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
    await expect(hermes).resolves.toMatchObject({ ok: true, items: [] });

    const jelly = api.listJellyseerrDiscover('trending');
    http.expectOne('/api/discover/jellyseerr?kind=trending').flush({ ok: true, enabled: false, items: [] });
    await expect(jelly).resolves.toMatchObject({ ok: true, availability: 'disabled' });

    const trakt = api.listTraktDiscover('movies');
    http.expectOne('/api/discover/trakt?type=movies').flush({
      ok: true,
      items: [],
      library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
    await expect(trakt).resolves.toMatchObject({ ok: true });

    const more = api.requestHermesMore();
    const moreReq = http.expectOne('/api/discover/hermes/request-more');
    expect(moreReq.request.method).toBe('POST');
    moreReq.flush({ ok: true, queued: true });
    await expect(more).resolves.toMatchObject({ ok: true, queued: true });
  });

  it('preserves trakt_slug through live transport mapping', async () => {
    const trakt = api.listTraktDiscover('shows');
    http
      .expectOne('/api/discover/trakt?type=shows')
      .flush({
        ok: true,
        items: [{ type: 'tv', title: 'Severance', tmdb_id: 95396, trakt_slug: 'severance', poster_url: null, rating: null }],
        library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
        watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      });
    const result = await trakt;
    expect(result.ok).toBe(true);
    expect(result.items).toHaveLength(1);
    expect(result.items[0].trakt_slug).toBe('severance');
  });

  it('sanitizes failed external browse transport text and preserves only reconnect code', async () => {
    const failed = api.listTraktDiscover('movies');
    http.expectOne('/api/discover/trakt?type=movies').flush(
      { error: '<script>alert(1)</script>', code: 'backend_secret' },
      { status: 503, statusText: 'Unavailable' },
    );
    await expect(failed).rejects.toThrow('Discover is temporarily unavailable. Try again.');
    await expect(failed).rejects.not.toThrow('backend_secret');

    const reconnect = api.listTraktDiscover('movies');
    http.expectOne('/api/discover/trakt?type=movies').flush(
      { error: 'internal details', code: 'reconnect_required' },
      { status: 401, statusText: 'Unauthorized' },
    );
    await expect(reconnect).rejects.toMatchObject({
      message: 'Trakt reconnect required',
      code: 'reconnect_required',
    });

    const softReconnect = api.listTraktDiscover('movies');
    http.expectOne('/api/discover/trakt?type=movies').flush({
      ok: false,
      error: '<script>secret</script>',
      code: 'reconnect_required',
    });
    await expect(softReconnect).resolves.toMatchObject({ ok: false, code: 'reconnect_required' });
  });

  it('returns soft ok:false envelopes for discover actions and cron logs', async () => {
    const feedback = api.submitHermesFeedback('missing', 'liked');
    http.expectOne('/api/discover/hermes/missing').flush({ ok: false, error: 'Recommendation not found' });
    await expect(feedback).resolves.toEqual({ ok: false, error: 'Recommendation not found' });

    const request = api.requestMedia({ mediaType: 'movie', mediaId: 1 });
    http.expectOne('/api/discover/request').flush({ ok: false, error: 'Cannot request' });
    await expect(request).resolves.toEqual({ ok: false, error: 'Cannot request' });

    const more = api.requestHermesMore();
    http.expectOne('/api/discover/hermes/request-more').flush({ ok: false, error: 'queue full' });
    await expect(more).resolves.toEqual({ ok: false, error: 'queue full' });

    const hermes = api.listHermesRecommendations();
    http.expectOne('/api/discover/hermes').flush({ ok: false, error: 'hermes down', items: [] });
    await expect(hermes).resolves.toMatchObject({ ok: false, error: 'hermes down' });

    const logs = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({ ok: false, error: 'no logs', logs: [] });
    await expect(logs).resolves.toMatchObject({ ok: false, error: 'no logs' });
  });

  it('maps automation ok:false when nested service blocks are present', async () => {
    const pending = api.getAutomationSummary();
    flushAutomationSummary(
      {
        ok: false,
        error: 'partial outage',
        generatedAt: '2026-07-13T12:00:00Z',
        sonarr: { ok: true, missing: 0, monitored: 1, queued: 0 },
        radarr: { ok: false, error: 'radarr down' },
        prowlarr: { ok: true, indexers: 1, enabled: 1 },
        bazarr: { ok: true, wantedEpisodes: 0, wantedMovies: 0 },
      },
      { jellyfinOk: false, qbitOk: true },
    );
    const summary = await pending;
    expect(summary.generatedAt).toBe('2026-07-13T12:00:00Z');
    expect(summary.services.find((s) => s.id === 'radarr')).toMatchObject({ status: 'down' });
    expect(summary.services.find((s) => s.id === 'jellyfin')).toMatchObject({ status: 'down' });
    expect(summary.services.find((s) => s.id === 'qbittorrent')).toMatchObject({ status: 'healthy' });
    expect(summary.problems.some((p) => p.id === 'automation-global')).toBe(true);
  });

  it('keeps jellyfin movies when series fails and labels the list partial', async () => {
    const pending = api.listLibraryItems();
    const movieReq = http.expectOne('/api/jellyfin/movies');
    const seriesReq = http.expectOne('/api/jellyfin/series');
    movieReq.flush({ ok: true, items: [{ id: 'm1', name: 'Movie' }] });
    seriesReq.flush({ ok: false, error: 'series offline' });
    await expect(pending).resolves.toEqual({
      availability: 'partial',
      movieCount: 1,
      seriesCount: undefined,
      items: [expect.objectContaining({ id: 'm1', kind: 'movie' })],
    });
  });

  it('rejects unfiltered library list when abort cancels one jellyfin kind mid-flight', async () => {
    const abort = new AbortController();
    const pending = api.listLibraryItems(undefined, abort.signal);
    const movieReq = http.expectOne('/api/jellyfin/movies');
    http.expectOne('/api/jellyfin/series');
    movieReq.flush({ ok: true, items: [{ id: 'm1', name: 'Movie' }] });
    abort.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('rejects library list only when both jellyfin kinds fail', async () => {
    const pending = api.listLibraryItems();
    http.expectOne('/api/jellyfin/movies').flush({ ok: false, error: 'movies down' });
    http.expectOne('/api/jellyfin/series').flush({ error: 'series boom' }, { status: 500, statusText: 'Err' });
    await expect(pending).rejects.toThrow();
  });

  it('rejects jellyfin members that lack required identity', async () => {
    const pending = api.listLibraryItems({ kind: 'movie' });
    http.expectOne('/api/jellyfin/movies').flush({ ok: true, items: [{ name: 'Movie' }] });
    await expect(pending).rejects.toThrow(/missing id/);
  });

  it('surfaces HTTP and void-action ok:false failures as rejected promises', async () => {
    const httpFail = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({ error: 'boom' }, { status: 500, statusText: 'Server Error' });
    await expect(httpFail).rejects.toThrow('boom');

    const actionFail = api.pauseAll();
    http.expectOne('/api/stop-all').flush({ ok: false, error: 'token required' });
    await expect(actionFail).rejects.toThrow('token required');
  });

  it('rejects null mutation responses instead of inventing success', async () => {
    const pending = api.requestHermesMore();
    http.expectOne('/api/discover/hermes/request-more').flush(null);
    await expect(pending).rejects.toThrow(/Malformed response/);
  });

  it('rejects discover actions missing a boolean ok field', async () => {
    const pending = api.submitHermesFeedback('rec-1', 'liked');
    http.expectOne('/api/discover/hermes/rec-1').flush({ error: 'nope' });
    await expect(pending).rejects.toThrow(/Malformed response/);
  });

  it('rejects soft envelopes that are null, primitives, or missing ok', async () => {
    const nullLogs = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush(null);
    await expect(nullLogs).rejects.toThrow(/Malformed response/);

    const stringLogs = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush('oops');
    await expect(stringLogs).rejects.toThrow(/Malformed response/);

    const missingOk = api.listHermesRecommendations();
    http.expectOne('/api/discover/hermes').flush({ items: [] });
    await expect(missingOk).rejects.toThrow(/Malformed response/);
  });

  it('rejects malformed list payloads inside soft envelopes', async () => {
    const badLogs = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({ ok: true, logs: 'nope' });
    await expect(badLogs).rejects.toThrow(/Malformed cron logs/);

    const badHermes = api.listHermesRecommendations();
    http.expectOne('/api/discover/hermes').flush({ ok: true, items: {} });
    await expect(badHermes).rejects.toThrow(/Malformed Hermes/);
  });

  it('rejects void mutations with null or invalid envelopes', async () => {
    const nullPause = api.pauseAll();
    http.expectOne('/api/stop-all').flush(null);
    await expect(nullPause).rejects.toThrow(/Malformed response/);

    const invalidPause = api.pauseAll();
    http.expectOne('/api/stop-all').flush({ success: true });
    await expect(invalidPause).rejects.toThrow(/Malformed response/);
  });

  it('rejects torrents when the payload is neither an array nor a failed envelope', async () => {
    const pending = api.listTorrents();
    http.expectOne('/api/qbt/torrents').flush({ unexpected: true });
    await expect(pending).rejects.toThrow(/Malformed/);
  });

  it('rejects ok:true soft envelopes that lack a required array', async () => {
    const missingLogs = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({ ok: true });
    await expect(missingLogs).rejects.toThrow(/Malformed cron logs/);

    const missingItems = api.listHermesRecommendations();
    http.expectOne('/api/discover/hermes').flush({ ok: true });
    await expect(missingItems).rejects.toThrow(/Malformed Hermes/);
  });

  it('preserves ok:false soft envelopes without success-only payload fields', async () => {
    const logs = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({ ok: false, error: 'no logs' });
    await expect(logs).resolves.toMatchObject({ ok: false, error: 'no logs' });

    const hermes = api.listHermesRecommendations();
    http.expectOne('/api/discover/hermes').flush({ ok: false, error: 'hermes down' });
    await expect(hermes).resolves.toMatchObject({ ok: false, error: 'hermes down' });
  });

  it('accepts valid empty arrays in ok:true soft envelopes', async () => {
    const logs = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({ ok: true, generatedAt: '2026-07-13T12:00:00Z', logs: [] });
    await expect(logs).resolves.toMatchObject({ ok: true, currentRuns: [] });

    const hermes = api.listHermesRecommendations();
    http.expectOne('/api/discover/hermes').flush({
      ok: true,
      items: [],
      library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
    await expect(hermes).resolves.toMatchObject({
      ok: true,
      items: [],
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
  });

  it('requires valid watched exclusion state on successful Hermes envelopes', async () => {
    for (const payload of [
      { ok: true, items: [], library_exclusion: { status: 'fresh', last_successful_refresh_at: null } },
      { ok: true, items: [], library_exclusion: { status: 'fresh', last_successful_refresh_at: null }, watched_exclusion: null },
      { ok: true, items: [], library_exclusion: { status: 'fresh', last_successful_refresh_at: null }, watched_exclusion: { status: 'broken', last_successful_refresh_at: null } },
    ]) {
      const pending = api.listHermesRecommendations();
      http.expectOne('/api/discover/hermes').flush(payload);
      await expect(pending).rejects.toThrow(/watched_exclusion/);
    }
  });

  it('rejects discover members missing required identity fields', async () => {
    const missingTitle = api.listHermesRecommendations();
    http.expectOne('/api/discover/hermes').flush({
      ok: true,
      library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      items: [
        {
          id: 'hermes-1',
          source: 'hermes',
          type: 'movie',
          tmdb_id: 101,
          active: true,
          added_at: '2026-07-10T12:00:00Z',
        },
      ],
    });
    await expect(missingTitle).rejects.toThrow(/missing title/);

    const missingTmdb = api.listJellyseerrDiscover('trending');
    http.expectOne('/api/discover/jellyseerr?kind=trending').flush({
      ok: true,
      items: [{ type: 'movie', title: 'Untitled' }],
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
    await expect(missingTmdb).rejects.toThrow(/missing tmdb_id/);

    const badType = api.listTraktDiscover('movies');
    http.expectOne('/api/discover/trakt?type=movies').flush({
      ok: true,
      items: [{ type: 'anime', title: 'Bad', tmdb_id: 9 }],
      library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
    await expect(badType).rejects.toThrow(/missing type/);
  });

  it('maps valid Hermes members including history fields', async () => {
    const pending = api.listHermesRecommendations();
    http.expectOne('/api/discover/hermes').flush({
      ok: true,
      items: [
        {
          id: 'hermes-1',
          source: 'hermes',
          type: 'movie',
          title: 'Signal Drift',
          tmdb_id: 101001,
          active: true,
          feedback: null,
          feedback_at: null,
          request_state: null,
          requested_at: null,
          jellyseerr_request_id: null,
          added_at: '2026-07-10T12:00:00Z',
          watched_on_trakt: true,
          excluded_reason: 'watched_on_trakt',
        },
      ],
      pending_request_sync: [{ id: 'hermes-1', jellyseerr_request_id: 55 }],
      generation_request: { requested_at: '2026-07-12T00:00:00Z', status: 'pending' },
      library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      watched_exclusion: { status: 'stale', last_successful_refresh_at: '2026-07-11T12:00:00Z' },
    });
    await expect(pending).resolves.toMatchObject({
      ok: true,
      items: [expect.objectContaining({ id: 'hermes-1', title: 'Signal Drift' })],
      pending_request_sync: [{ id: 'hermes-1', jellyseerr_request_id: 55 }],
      generation_request: { status: 'pending' },
      watched_exclusion: { status: 'stale', last_successful_refresh_at: '2026-07-11T12:00:00Z' },
    });
  });

  it('rejects invalid Hermes watched projection state', async () => {
    const pending = api.listHermesRecommendations();
    http.expectOne('/api/discover/hermes').flush({
      ok: true,
      items: [{
        id: 'hermes-1',
        source: 'hermes',
        type: 'movie',
        title: 'Signal Drift',
        tmdb_id: 101001,
        active: false,
        feedback: null,
        feedback_at: null,
        request_state: null,
        requested_at: null,
        jellyseerr_request_id: null,
        added_at: '2026-07-10T12:00:00Z',
        watched_on_trakt: 'yes',
        excluded_reason: 'watched_on_trakt',
      }],
    });
    await expect(pending).rejects.toThrow(/watched_on_trakt/);
  });

  it('rejects cron log members missing required identity or current/history', async () => {
    const missingGeneratedAt = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({ ok: true, logs: [] });
    await expect(missingGeneratedAt).rejects.toThrow(/missing generatedAt/);

    const missingJobId = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      logs: [
        {
          title: 'Watchdog',
          file: 'w.log',
          format: 'ndjson',
          schedule: '* * * * *',
          exists: true,
          current: { status: 'ok', detail: 'ok' },
          history: [],
        },
      ],
    });
    await expect(missingJobId).rejects.toThrow(/missing id/);

    const missingCurrent = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      logs: [{ id: 'watchdog', title: 'Watchdog', file: 'w.log', format: 'ndjson', schedule: '* * * * *', exists: true, history: [] }],
    });
    await expect(missingCurrent).rejects.toThrow(/invalid current/);

    const missingHistory = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      logs: [
        { id: 'watchdog', title: 'Watchdog', file: 'w.log', format: 'ndjson', schedule: '* * * * *', exists: true, current: { status: 'ok' } },
      ],
    });
    await expect(missingHistory).rejects.toThrow(/invalid history/);
  });

  it('accepts cron run rows without timestamps and maps them as unknown-time', async () => {
    const logs = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      logs: [
        {
          id: 'watchdog',
          title: 'Watchdog',
          file: 'w.log',
          format: 'ndjson',
          schedule: '* * * * *',
          exists: true,
          current: { status: 'ok', detail: 'All services are healthy' },
          history: [{ status: 'fatal', detail: 'old failure', fatal: 'old failure' }],
        },
      ],
    });
    await expect(logs).resolves.toMatchObject({
      currentRuns: [{ jobId: 'watchdog', status: 'ok', timestamp: '' }],
      historyRuns: [{ jobId: 'watchdog', status: 'fatal', resolved: true }],
    });
  });

  it('rejects malformed automation summaries at the HTTP boundary', async () => {
    const primitive = api.getAutomationSummary();
    http.expectOne('/api/automation/summary').flush('nope');
    flushSidebarProbes();
    await expect(primitive).rejects.toThrow(/Malformed automation summary/);

    const array = api.getAutomationSummary();
    http.expectOne('/api/automation/summary').flush([{ ok: true }]);
    flushSidebarProbes();
    await expect(array).rejects.toThrow(/Malformed automation summary/);

    const emptyObject = api.getAutomationSummary();
    http.expectOne('/api/automation/summary').flush({});
    flushSidebarProbes();
    await expect(emptyObject).rejects.toThrow(/Malformed automation summary/);

    const missingOk = api.getAutomationSummary();
    http.expectOne('/api/automation/summary').flush({ sonarr: { ok: true } });
    flushSidebarProbes();
    await expect(missingOk).rejects.toThrow(/Malformed automation summary/);

    const okTrueNoServices = api.getAutomationSummary();
    http.expectOne('/api/automation/summary').flush({ ok: true, generatedAt: '2026-07-13T12:00:00Z' });
    flushSidebarProbes();
    await expect(okTrueNoServices).rejects.toThrow(/Malformed automation summary/);

    const invalidService = api.getAutomationSummary();
    http.expectOne('/api/automation/summary').flush({ ok: true, sonarr: 'down' });
    flushSidebarProbes();
    await expect(invalidService).rejects.toThrow(/Malformed automation summary/);

    const invalidGeneratedAt = api.getAutomationSummary();
    http.expectOne('/api/automation/summary').flush({
      ok: true,
      generatedAt: 'not-a-date',
      sonarr: { ok: true, missing: 0, monitored: 1, queued: 0 },
    });
    flushSidebarProbes();
    await expect(invalidGeneratedAt).rejects.toThrow(/invalid generatedAt/);
  });

  it('preserves backend error for automation ok:false without full summary', async () => {
    const pending = api.getAutomationSummary();
    http.expectOne('/api/automation/summary').flush({ ok: false, error: 'automation backend unavailable' });
    flushSidebarProbes();
    await expect(pending).rejects.toThrow('automation backend unavailable');
  });

  it('accepts partial automation summaries when ok:true and some service blocks are present', async () => {
    const pending = api.getAutomationSummary();
    flushAutomationSummary({
      ok: true,
      generatedAt: '2026-07-13T12:00:00Z',
      sonarr: { ok: true, missing: 0, monitored: 1, queued: 0 },
    });
    const summary = await pending;
    const sonarr = summary.services.find((s) => s.id === 'sonarr');
    expect(sonarr).toMatchObject({ status: 'healthy' });
    expect(summary.services.find((s) => s.id === 'jellyfin')).toMatchObject({ status: 'healthy' });
    expect(summary.generatedAt).toBe('2026-07-13T12:00:00Z');
  });

  it('rejects with a stable Error on a real transport network failure', async () => {
    const pending = api.listTorrents();
    const req = http.expectOne('/api/qbt/torrents');
    req.error(new ProgressEvent('error'));
    await expect(pending).rejects.toSatisfy((error: unknown) => {
      if (!(error instanceof Error)) return false;
      return error.message.includes('/api/qbt/torrents');
    });
  });

  it('GETs jellyfin watch-next and maps progress items', async () => {
    const pending = api.listWatchNext();
    const req = http.expectOne('/api/jellyfin/watch-next');
    req.flush({
      ok: true,
      items: [
        {
          id: 'ep-1',
          parentId: 'series-1',
          title: 'The Expanse',
          subtitle: 'S04E02 · Jetsam',
          kind: 'episode',
          image: '/img',
          playable: true,
          progressPercent: 42,
        },
      ],
    });
    const result = await pending;
    expect(result.items).toHaveLength(1);
    expect(result.items[0]).toMatchObject({
      id: 'ep-1',
      title: 'The Expanse',
      subtitle: 'S04E02 · Jetsam',
      kind: 'episode',
      progressPercent: 42,
    });
  });

  it('rejects malformed watch-next envelopes and members', async () => {
    const malformedEnvelope = api.listWatchNext();
    http.expectOne('/api/jellyfin/watch-next').flush({ ok: false, error: 'watch-next unavailable' });
    await expect(malformedEnvelope).rejects.toThrow('watch-next unavailable');

    const malformedMember = api.listWatchNext();
    http.expectOne('/api/jellyfin/watch-next').flush({
      ok: true,
      items: [{ id: 'ep-1', parentId: 'series-1', title: 'Show', kind: 'episode', progressPercent: null }],
    });
    await expect(malformedMember).rejects.toThrow(/missing progressPercent/);
  });

  it('aborts in-flight watch-next requests', async () => {
    const abort = new AbortController();
    const pending = api.listWatchNext(abort.signal);
    http.expectOne('/api/jellyfin/watch-next');
    abort.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('GETs jellyfin recently-available with normalized limit and maps items', async () => {
    const pending = api.listRecentlyAvailable(51);
    const req = http.expectOne('/api/jellyfin/recently-available?limit=50');
    req.flush({
      ok: true,
      items: [
        {
          id: 'ep-1',
          parentId: 'series-1',
          title: 'Saga of Tanya the Evil',
          subtitle: 'S02E05 · Lamb',
          kind: 'episode',
          image: '/img',
          thumbUrl: '/thumb',
          availableAt: '2026-08-11T12:14:33Z',
          playable: true,
          year: 2026,
        },
        {
          id: 'mv-1',
          parentId: null,
          title: 'Mickey 17',
          subtitle: '',
          kind: 'movie',
          image: '/movie',
          thumbUrl: null,
          availableAt: '2026-08-10T08:00:00Z',
          playable: true,
          year: 2025,
        },
      ],
    });
    const result = await pending;
    expect(result.items.map((item) => item.id)).toEqual(['ep-1', 'mv-1']);
    expect(result.items[0]).toMatchObject({
      title: 'Saga of Tanya the Evil',
      href: null,
      playable: true,
    });
  });

  it('rejects malformed recently-available envelopes and members', async () => {
    const malformedEnvelope = api.listRecentlyAvailable();
    http.expectOne('/api/jellyfin/recently-available?limit=10').flush({
      ok: false,
      error: 'recently unavailable',
    });
    await expect(malformedEnvelope).rejects.toThrow('recently unavailable');

    const malformedMember = api.listRecentlyAvailable();
    http.expectOne('/api/jellyfin/recently-available?limit=10').flush({
      ok: true,
      items: [{ id: 'ep-1', parentId: 'series-1', title: 'Show', kind: 'episode', playable: true }],
    });
    await expect(malformedMember).rejects.toThrow(/availableAt/);
  });

  it('aborts in-flight recently-available requests', async () => {
    const abort = new AbortController();
    const pending = api.listRecentlyAvailable(10, abort.signal);
    http.expectOne('/api/jellyfin/recently-available?limit=10');
    abort.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('GETs the activity feed and maps merged items', async () => {
    const pending = api.getActivity();
    const req = http.expectOne('/api/activity?limit=20');
    req.flush({
      ok: true,
      generatedAt: '2026-07-30T00:20:00Z',
      sources: { sonarr: 'ok', radarr: 'ok' },
      items: [
        {
          id: 'sonarr:48211',
          source: 'sonarr',
          kind: 'grabbed',
          title: 'The Shōgun Court',
          subtitle: 'S01E07 · 1080p WEB-DL',
          timestamp: '2026-07-30T00:18:41Z',
          href: 'http://localhost:8989/series/the-shogun-court',
        },
      ],
    });
    const feed = await pending;
    expect(feed.ok).toBe(true);
    expect(feed.sources).toEqual({ sonarr: 'ok', radarr: 'ok' });
    expect(feed.items).toHaveLength(1);
    expect(feed.items[0]).toMatchObject({ id: 'sonarr:48211', kind: 'grabbed', title: 'The Shōgun Court' });
  });

  it('passes a clamped activity limit and keeps per-source error status', async () => {
    const pending = api.getActivity(500);
    const req = http.expectOne('/api/activity?limit=50');
    req.flush({
      ok: true,
      generatedAt: '2026-07-30T00:20:00Z',
      sources: { sonarr: 'error', radarr: 'ok' },
      items: [],
    });
    const feed = await pending;
    expect(feed.sources).toEqual({ sonarr: 'error', radarr: 'ok' });
    expect(feed.items).toEqual([]);
  });

  it('rejects malformed activity members', async () => {
    const pending = api.getActivity();
    http.expectOne('/api/activity?limit=20').flush({
      ok: true,
      sources: { sonarr: 'ok', radarr: 'ok' },
      items: [{ id: 'sonarr:1', source: 'sonarr', kind: 'mystery', title: 'Show', timestamp: '2026-07-30T00:18:41Z' }],
    });
    await expect(pending).rejects.toThrow(/invalid kind/);
  });
});
