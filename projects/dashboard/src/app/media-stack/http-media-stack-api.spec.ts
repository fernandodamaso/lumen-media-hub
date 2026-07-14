import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { HttpMediaStackApi } from './http-media-stack-api';
import { mapLiveAutomationSummary, mapLiveJellyfinItem, mapLiveTorrent } from './live-api.mappers';

describe('live-api.mappers', () => {
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

  it('maps jellyfin items with artwork state', () => {
    expect(mapLiveJellyfinItem({ id: '1', name: 'Dune', year: 2021, image: '/img' }, 'movie')).toEqual({
      id: '1',
      title: 'Dune',
      kind: 'movie',
      year: 2021,
      posterUrl: '/img',
      artworkState: 'ok',
      playable: true,
    });
    expect(mapLiveJellyfinItem({ id: '2', name: 'Show' }, 'series').artworkState).toBe('missing');
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
  });

  it('rejects a failed automation envelope with no service blocks', () => {
    expect(() => mapLiveAutomationSummary({ ok: false, error: 'backend down' })).toThrow('backend down');
  });

  it('maps automation ok:false when nested service blocks remain', () => {
    const dto = mapLiveAutomationSummary({
      ok: false,
      error: 'partial outage',
      sonarr: { ok: true, missing: 0, monitored: 2, queued: 0 },
      radarr: { ok: false, error: 'timeout' },
    });
    expect(dto.services?.find((s) => s.id === 'sonarr')?.status).toBe('healthy');
    expect(dto.services?.find((s) => s.id === 'radarr')?.status).toBe('down');
    expect(dto.problems?.some((p) => p.summary === 'partial outage')).toBe(true);
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
      expect.objectContaining({ hash: 'h1', downloaded: 100, progress: 0.25 }),
    ]);
  });

  it('rejects torrents when envelope ok is false', async () => {
    const pending = api.listTorrents();
    http.expectOne('/api/qbt/torrents').flush({ ok: false, error: 'qbt down' });
    await expect(pending).rejects.toThrow('qbt down');
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

  it('unwraps calendar envelope and rejects ok:false', async () => {
    const pending = api.listCalendarEvents();
    http.expectOne('/api/sonarr/calendar').flush({
      ok: true,
      events: [{ title: 'Show', additional: 'S01E01', date: '20:00', airDate: '2026-07-13' }],
    });
    await expect(pending).resolves.toEqual([
      expect.objectContaining({ title: 'Show', additional: 'S01E01' }),
    ]);

    const failed = api.listCalendarEvents();
    http.expectOne('/api/sonarr/calendar').flush({ ok: false, error: 'sonarr offline' });
    await expect(failed).rejects.toThrow('sonarr offline');
  });

  it('GETs arr library and cron logs', async () => {
    const library = api.getArrLibrary();
    http.expectOne('/api/arr/library').flush({ ok: true, series: { show: 'slug' }, movies: {} });
    await expect(library).resolves.toMatchObject({ ok: true, series: { show: 'slug' } });

    const logs = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({ ok: true, logs: [] });
    await expect(logs).resolves.toMatchObject({ ok: true, logs: [] });
  });

  it('merges jellyfin movies and series for listLibraryItems', async () => {
    const pending = api.listLibraryItems();
    const movieReq = http.expectOne('/api/jellyfin/movies');
    const seriesReq = http.expectOne('/api/jellyfin/series');
    movieReq.flush({ ok: true, items: [{ id: 'm1', name: 'Movie', year: 2020, image: '/m' }] });
    seriesReq.flush({ ok: true, items: [{ id: 's1', name: 'Series' }] });
    const items = await pending;
    expect(items).toEqual([
      expect.objectContaining({ id: 'm1', kind: 'movie', title: 'Movie' }),
      expect.objectContaining({ id: 's1', kind: 'series', title: 'Series', artworkState: 'missing' }),
    ]);
  });

  it('filters jellyfin requests by kind', async () => {
    const moviesOnly = api.listLibraryItems({ kind: 'movie' });
    http.expectOne('/api/jellyfin/movies').flush({ ok: true, items: [{ id: 'm1', name: 'Movie' }] });
    http.expectNone('/api/jellyfin/series');
    await expect(moviesOnly).resolves.toHaveLength(1);

    const seriesOnly = api.listLibraryItems({ kind: 'series' });
    http.expectOne('/api/jellyfin/series').flush({ ok: true, items: [{ id: 's1', name: 'Series' }] });
    http.expectNone('/api/jellyfin/movies');
    await expect(seriesOnly).resolves.toHaveLength(1);
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

  it('maps automation summary from nested live payload', async () => {
    const pending = api.getAutomationSummary();
    http.expectOne('/api/automation/summary').flush({
      ok: true,
      sonarr: { ok: true, missing: 0, monitored: 1, queued: 0 },
      radarr: { ok: true, movies: 1, missing: 0, queued: 0 },
      prowlarr: { ok: true, indexers: 1, enabled: 1 },
      bazarr: { ok: true, wantedEpisodes: 0, wantedMovies: 0 },
    });
    const summary = await pending;
    expect(summary.services).toHaveLength(4);
    expect(summary.services?.every((s) => s.status === 'healthy')).toBe(true);
  });

  it('keeps discover feedback PATCH separate from requestMedia POST', async () => {
    const feedback = api.submitHermesFeedback('rec-1', 'liked', 'great');
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

  it('loads discover sources and request-more', async () => {
    const hermes = api.listHermesRecommendations();
    http.expectOne('/api/discover/hermes').flush({ ok: true, items: [] });
    await expect(hermes).resolves.toMatchObject({ ok: true, items: [] });

    const jelly = api.listJellyseerrDiscover('trending');
    http.expectOne('/api/discover/jellyseerr?kind=trending').flush({ ok: true, items: [] });
    await expect(jelly).resolves.toMatchObject({ ok: true });

    const trakt = api.listTraktDiscover('movies');
    http.expectOne('/api/discover/trakt?type=movies').flush({ ok: true, items: [] });
    await expect(trakt).resolves.toMatchObject({ ok: true });

    const more = api.requestHermesMore();
    const moreReq = http.expectOne('/api/discover/hermes/request-more');
    expect(moreReq.request.method).toBe('POST');
    moreReq.flush({ ok: true, queued: true });
    await expect(more).resolves.toMatchObject({ ok: true, queued: true });
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
    http.expectOne('/api/automation/summary').flush({
      ok: false,
      error: 'partial outage',
      sonarr: { ok: true, missing: 0, monitored: 1, queued: 0 },
      radarr: { ok: false, error: 'radarr down' },
      prowlarr: { ok: true, indexers: 1, enabled: 1 },
      bazarr: { ok: true, wantedEpisodes: 0, wantedMovies: 0 },
    });
    const summary = await pending;
    expect(summary.services?.find((s) => s.id === 'radarr')).toMatchObject({ status: 'down' });
    expect(summary.problems?.some((p) => p.id === 'automation-global')).toBe(true);
  });

  it('keeps jellyfin movies when series fails', async () => {
    const pending = api.listLibraryItems();
    const movieReq = http.expectOne('/api/jellyfin/movies');
    const seriesReq = http.expectOne('/api/jellyfin/series');
    movieReq.flush({ ok: true, items: [{ id: 'm1', name: 'Movie' }] });
    seriesReq.flush({ ok: false, error: 'series offline' });
    await expect(pending).resolves.toEqual([expect.objectContaining({ id: 'm1', kind: 'movie' })]);
  });

  it('rejects library list only when both jellyfin kinds fail', async () => {
    const pending = api.listLibraryItems();
    http.expectOne('/api/jellyfin/movies').flush({ ok: false, error: 'movies down' });
    http.expectOne('/api/jellyfin/series').flush({ error: 'series boom' }, { status: 500, statusText: 'Err' });
    await expect(pending).rejects.toThrow();
  });

  it('surfaces HTTP and void-action ok:false failures as rejected promises', async () => {
    const httpFail = api.listCronLogs();
    http.expectOne('/api/cron/logs').flush({ error: 'boom' }, { status: 500, statusText: 'Server Error' });
    await expect(httpFail).rejects.toThrow('boom');

    const actionFail = api.pauseAll();
    http.expectOne('/api/stop-all').flush({ ok: false, error: 'token required' });
    await expect(actionFail).rejects.toThrow('token required');
  });
});
