import { vi } from 'vitest';
import { summarizeDownloads } from '../downloads/downloads.models';
import { MediaStackApi } from './media-stack-api';
import { MockMediaStackApi, MOCK_SYNC_FAILED_HERMES_ID } from './mock-media-stack-api';

function createApi(): MockMediaStackApi {
  const api = new MockMediaStackApi();
  api.latencyMs = 0;
  return api;
}

describe('MockMediaStackApi', () => {
  it('delays reads by latencyMs with jitter, and resolves immediately at zero', async () => {
    vi.useFakeTimers();
    try {
      const api = createApi();
      api.latencyMs = 500;

      let resolved = false;
      const pending = api.listTorrents().then((torrents) => {
        resolved = true;
        return torrents;
      });

      await vi.advanceTimersByTimeAsync(299); // below minimum jitter (500 * 0.6)
      expect(resolved).toBe(false);

      await vi.advanceTimersByTimeAsync(500); // past maximum jitter (500 * 1.4)
      expect(resolved).toBe(true);
      await expect(pending).resolves.toHaveLength(3);

      api.latencyMs = 0;
      let immediate = false;
      const fast = api.listTorrents().then(() => {
        immediate = true;
      });
      await vi.advanceTimersByTimeAsync(0);
      expect(immediate).toBe(true);
      await fast;
    } finally {
      vi.useRealTimers();
    }
  });

  it('provides deterministic torrents and supports pause/resume all', async () => {
    const api: MediaStackApi = createApi();
    const initial = await api.listTorrents();
    expect(initial.map((torrent) => torrent.id)).toEqual(['demo-afterlight', 'demo-blue-hour', 'demo-orbit']);
    expect(initial.filter((torrent) => torrent.state === 'downloading')).toHaveLength(2);
    expect(initial.find((torrent) => torrent.id === 'demo-orbit')).toMatchObject({
      state: 'seeding',
      progress: 100,
      downloadRate: 0,
    });

    await api.pauseAll();
    const paused = await api.listTorrents();
    expect(paused.every((torrent) => torrent.state === 'paused' && torrent.downloadRate === 0 && torrent.uploadRate === 0)).toBe(
      true,
    );
    expect(summarizeDownloads(paused)).toMatchObject({ downloadRate: 0, uploadRate: 0 });
    await api.resumeAll();
    const resumed = await api.listTorrents();
    expect(resumed.map(({ id, downloadRate, uploadRate }) => ({ id, downloadRate, uploadRate }))).toEqual(
      initial.map(({ id, downloadRate, uploadRate }) => ({ id, downloadRate, uploadRate })),
    );
  });

  it('pauses and resumes a single torrent statefully', async () => {
    const api: MediaStackApi = createApi();
    const [before] = await api.listTorrents();

    await api.pauseTorrent(before.id);
    const paused = await api.listTorrents();
    expect(paused[0]).toMatchObject({ id: before.id, state: 'paused', downloadRate: 0, uploadRate: 0 });
    expect(paused[1].state).toBe('downloading');

    await api.resumeTorrent(before.id);
    const resumed = await api.listTorrents();
    expect(resumed[0]).toMatchObject({
      id: before.id,
      state: 'downloading',
      downloadRate: before.downloadRate,
      uploadRate: before.uploadRate,
    });

    await api.pauseTorrent('demo-orbit');
    await api.resumeTorrent('demo-orbit');
    const seeding = await api.listTorrents();
    expect(seeding.find((torrent) => torrent.id === 'demo-orbit')?.state).toBe('seeding');
  });

  it('provides ordered mixed calendar events and arr library mappings', async () => {
    const api: MediaStackApi = createApi();
    const events = await api.listCalendarEvents();
    expect(events.map((event) => event.title)).toEqual([
      'Cowboy Bebop',
      'The Blue Hour',
      'Dune',
      'The Expanse',
    ]);
    expect(events.map((event) => event.status)).toEqual(['available', 'monitored', 'premiere', 'monitored']);
    expect(events.every((event) => event.art?.includes('gradient('))).toBe(true);
    expect(events.some((event) => event.kind === 'episode')).toBe(true);
    expect(events.some((event) => event.kind === 'movie')).toBe(true);

    const today = new Date();
    const bebop = events[0];
    expect(bebop.airDate.slice(0, 10)).toBe(
      `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`,
    );

    const library = await api.getArrLibrary();
    expect(library.series['cowboy bebop']).toBe('cowboy-bebop');
    expect(library.series['the blue hour']).toBe('the-blue-hour');
    expect(library.movies['dune']).toBe('dune-2021');
  });

  it('isolates discover fixtures across Hermes and external filters', async () => {
    const api = createApi();
    const hermes = await api.listHermesRecommendations();
    expect(hermes.ok).toBe(true);
    expect(hermes.items.some((item) => item.id === 'hermes-eligible' && item.active)).toBe(true);
    expect(hermes.items.some((item) => item.id === 'hermes-in-library' && item.in_library)).toBe(true);
    expect(hermes.items.some((item) => item.id === 'hermes-requested' && item.request_state === 'requested')).toBe(true);
    expect(hermes.items.some((item) => item.id === 'hermes-no-tmdb' && item.tmdb_id === 0)).toBe(true);
    expect(hermes.items.some((item) => item.id === MOCK_SYNC_FAILED_HERMES_ID)).toBe(true);
    expect(hermes.items.some((item) => !item.active && item.feedback === 'liked')).toBe(true);

    const jellyseerrTrending = await api.listJellyseerrDiscover('trending');
    const jellyseerrMovies = await api.listJellyseerrDiscover('movies');
    const jellyseerrTv = await api.listJellyseerrDiscover('tv');
    expect(jellyseerrTrending.items.map((item) => item.title)).toEqual(['Trending Ember', 'Trending Tide']);
    expect(jellyseerrMovies.items.map((item) => item.title)).toEqual(['Neon Archive', 'Paper Orbit']);
    expect(jellyseerrTv.items.map((item) => item.title)).toEqual(['Channel Zero Point', 'Late Broadcast']);
    expect(jellyseerrTrending.items.map((item) => item.tmdb_id)).not.toEqual(
      jellyseerrMovies.items.map((item) => item.tmdb_id),
    );

    const traktMovies = await api.listTraktDiscover('movies');
    const traktShows = await api.listTraktDiscover('shows');
    expect(traktMovies.items.map((item) => item.title)).toEqual(['Trakt Horizon', 'Trakt Meridian']);
    expect(traktShows.items.map((item) => item.title)).toEqual(['Trakt Relay', 'Trakt Cascade']);
  });

  it('keeps feedback mutation isolated from request fields', async () => {
    const api = createApi();
    const before = (await api.listHermesRecommendations()).items.find((item) => item.id === 'hermes-eligible');
    if (!before) throw new Error('hermes-eligible missing before feedback');
    const requestSnapshot = {
      request_state: before.request_state,
      requested_at: before.requested_at,
      jellyseerr_request_id: before.jellyseerr_request_id,
    };

    const result = await api.submitHermesFeedback('hermes-eligible', 'liked');
    expect(result.ok).toBe(true);

    const after = (await api.listHermesRecommendations()).items.find((item) => item.id === 'hermes-eligible');
    if (!after) throw new Error('hermes-eligible missing after feedback');
    expect(after.feedback).toBe('liked');
    expect(after.feedback_at).toBeTruthy();
    expect(after.active).toBe(false);
    expect(after.request_state).toBe(requestSnapshot.request_state);
    expect(after.requested_at).toBe(requestSnapshot.requested_at);
    expect(after.jellyseerr_request_id).toBe(requestSnapshot.jellyseerr_request_id);
  });

  it('requestMedia updates request fields without touching feedback', async () => {
    const api = createApi();
    const before = (await api.listHermesRecommendations()).items.find((item) => item.id === 'hermes-eligible');
    if (!before) throw new Error('hermes-eligible missing before request');
    expect(before.feedback).toBeNull();

    const result = await api.requestMedia({ mediaType: 'movie', mediaId: 101001, hermesId: 'hermes-eligible' });
    expect(result.ok).toBe(true);
    expect(result.dashboard_state_persisted).toBe(true);

    const after = (await api.listHermesRecommendations()).items.find((item) => item.id === 'hermes-eligible');
    if (!after) throw new Error('hermes-eligible missing after request');
    expect(after.request_state).toBe('requested');
    expect(after.requested_at).toBeTruthy();
    expect(after.jellyseerr_request_id).toBeTruthy();
    expect(after.feedback).toBeNull();
    expect(after.feedback_at).toBeNull();
  });

  it('simulates sync-failed partial success without writing request_state', async () => {
    const api = createApi();
    const result = await api.requestMedia({ mediaType: 'tv', mediaId: 101005, hermesId: MOCK_SYNC_FAILED_HERMES_ID });
    expect(result.ok).toBe(true);
    expect(result.dashboard_state_persisted).toBe(false);
    expect(result.partial_success).toBe(true);

    const after = (await api.listHermesRecommendations()).items.find((item) => item.id === MOCK_SYNC_FAILED_HERMES_ID);
    if (!after) throw new Error('sync-failed hermes item missing');
    expect(after.request_state).toBeNull();
    expect(after.jellyseerr_request_id).toBeTruthy();
  });

  it('requestHermesMore queues once then reports already_pending', async () => {
    const api = createApi();
    const first = await api.requestHermesMore();
    expect(first).toMatchObject({ ok: true, queued: true, already_pending: false });
    const second = await api.requestHermesMore();
    expect(second).toMatchObject({ ok: true, queued: false, already_pending: true });
    const hermes = await api.listHermesRecommendations();
    expect(hermes.generation_request?.status).toBe('pending');
  });

  it('dedupes external requests by TMDB id and media type', async () => {
    const api = createApi();
    const first = await api.requestMedia({ mediaType: 'movie', mediaId: 301001 });
    expect(first.ok).toBe(true);
    expect(first.message).toBe('Requested');
    const second = await api.requestMedia({ mediaType: 'movie', mediaId: 301001 });
    expect(second.message).toBe('Already requested');
  });

  it('provides deterministic automation summary with mixed service health', async () => {
    const api = createApi();
    const summary = await api.getAutomationSummary();
    expect(summary.generatedAt).toBeTruthy();
    expect(summary.services.map((service) => service.id)).toEqual([
      'jellyfin',
      'sonarr',
      'radarr',
      'prowlarr',
      'sabnzbd',
      'qbittorrent',
      'bazarr',
      'unpackerr',
    ]);
    expect(summary.services.some((service) => service.status === 'down')).toBe(true);
    expect(summary.services.some((service) => service.status === 'degraded')).toBe(true);
    expect(summary.services.find((service) => service.id === 'prowlarr')).toMatchObject({
      status: 'degraded',
      latencyMs: 350,
    });
    expect(summary.services.find((service) => service.id === 'sabnzbd')?.latencyMs).toBeNull();
    expect(summary.problems.some((problem) => problem.severity === 'actionable')).toBe(true);
    expect(summary.problems.filter((problem) => problem.serviceId === 'prowlarr')).toHaveLength(2);
    expect(summary.preview).toHaveLength(3);
  });

  it('provides a partial automation summary marking preview and problems unavailable', async () => {
    const api = createApi();
    api.setAutomationScenario('partial');
    const summary = await api.getAutomationSummary();
    expect(summary.services).toHaveLength(1);
    expect(summary.availability).toEqual({
      services: 'present',
      preview: 'unavailable',
      problems: 'unavailable',
    });
    expect(summary.preview).toEqual([]);
  });

  it('lists library items with kind filter and defensive copies', async () => {
    const api: MediaStackApi = createApi();
    const all = await api.listLibraryItems();
    expect(all.availability).toBe('complete');
    expect(all.items.filter((item) => item.kind === 'movie').length).toBeGreaterThanOrEqual(3);
    expect(all.items.filter((item) => item.kind === 'series').length).toBeGreaterThanOrEqual(3);
    expect(all.items.some((item) => item.artworkState === 'missing')).toBe(true);
    expect(all.items.some((item) => item.artworkState === 'failed')).toBe(true);

    const movies = await api.listLibraryItems({ kind: 'movie' });
    expect(movies.availability).toBe('complete');
    expect(movies.items.every((item) => item.kind === 'movie')).toBe(true);

    const first = movies.items[0];
    first.title = 'Mutated';
    const again = await api.listLibraryItems({ kind: 'movie' });
    expect(again.items[0].title).not.toBe('Mutated');
  });

  it('provides mixed cron-log history covering failures, actionable, and quiet runs', async () => {
    const api: MediaStackApi = createApi();
    const response = await api.listCronLogs();
    expect(response.ok).toBe(true);
    expect(response.generatedAt).toBeTruthy();
    expect([...new Set(response.runs.map((run) => run.jobId))]).toEqual([
      'hardlink-cleanup',
      'stale-metadata',
      'watchdog',
    ]);

    const statuses = response.runs.map((run) => run.status);
    expect(statuses).toContain('fatal');
    expect(statuses).toContain('applied');
    expect(statuses).toContain('ok');

    const failed = response.runs.find((run) => run.jobId === 'stale-metadata');
    expect(failed).toMatchObject({ triage: 'actionable', detail: '3 items failed to refresh' });
    const healthy = response.runs.find((run) => run.jobId === 'watchdog');
    expect(healthy).toMatchObject({ triage: 'quiet', detail: 'All services are healthy' });

    const again = await api.listCronLogs();
    again.runs[0].detail = 'mutated';
    const fresh = await api.listCronLogs();
    expect(fresh.runs[0].detail).not.toBe('mutated');
  });

  describe('downloads scenarios', () => {
    it('default scenario matches existing behavior', async () => {
      const api = createApi();
      const torrents = await api.listTorrents();
      expect(torrents).toHaveLength(3);
      expect(torrents.filter((t) => t.state === 'downloading')).toHaveLength(2);
      expect(torrents.filter((t) => t.state === 'seeding')).toHaveLength(1);
    });

    it('empty scenario returns no torrents', async () => {
      const api = createApi();
      api.setDownloadsScenario('empty');
      const torrents = await api.listTorrents();
      expect(torrents).toHaveLength(0);
    });

    it('error scenario rejects listTorrents', async () => {
      const api = createApi();
      api.setDownloadsScenario('error');
      await expect(api.listTorrents()).rejects.toThrow('qBittorrent unavailable');
    });

    it('paused scenario has all torrents paused with zero speeds', async () => {
      const api = createApi();
      api.setDownloadsScenario('paused');
      const torrents = await api.listTorrents();
      expect(torrents).toHaveLength(3);
      expect(torrents.every((t) => t.state === 'paused' && t.downloadRate === 0 && t.uploadRate === 0)).toBe(true);
    });

    it('mixed scenario has one torrent per canonical state', async () => {
      const api = createApi();
      api.setDownloadsScenario('mixed');
      const torrents = await api.listTorrents();
      expect(torrents).toHaveLength(6);
      const states = new Set(torrents.map((t) => t.state));
      expect(states).toEqual(new Set(['downloading', 'seeding', 'paused', 'queued', 'checking', 'error']));
    });

    it('pause/resume still work after switching scenarios', async () => {
      const api = createApi();

      api.setDownloadsScenario('paused');
      await api.resumeAll();
      const resumed = await api.listTorrents();
      expect(resumed.filter((t) => t.state === 'downloading' || t.state === 'seeding').length).toBeGreaterThan(0);

      api.setDownloadsScenario('default');
      await api.pauseAll();
      const paused = await api.listTorrents();
      expect(paused.every((t) => t.state === 'paused')).toBe(true);

      api.setDownloadsScenario('error');
      await expect(api.pauseAll()).resolves.toBeUndefined();
      await expect(api.resumeAll()).resolves.toBeUndefined();

      api.setDownloadsScenario('default');
      const restored = await api.listTorrents();
      expect(restored.filter((t) => t.state === 'downloading' || t.state === 'seeding').length).toBeGreaterThan(0);
    });
  });

  it('provides storage volumes and library stats', async () => {
    const api: MediaStackApi = createApi();
    const storage = await api.getStorageOverview();
    expect(storage.generatedAt).toBeTruthy();
    expect(storage.volumes.map((volume) => volume.kind)).toEqual(['library']);
    const library = storage.volumes[0];
    expect(library.id).toBe('media-volume');
    expect(library.label).toBe('Media volume (/data)');
    expect(library.usedBytes).toBeGreaterThan(4.5 * 1024 ** 4);
    expect(library.usedBytes).toBeLessThan(library.totalBytes);

    const stats = await api.getLibraryStats();
    expect(stats).toEqual({ movies: 428, series: 76, availability: 'complete' });
  });
});
