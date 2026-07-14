import { Injectable } from '@angular/core';
import {
  DiscoverFeedback,
  JellyseerrDiscoverKind,
  LibraryItemKind,
  MediaStackApi,
  MediaStackArrLibraryDto,
  MediaStackAutomationSummaryDto,
  MediaStackCalendarEventDto,
  MediaStackCronLogEntryDto,
  MediaStackCronLogsDto,
  MediaStackDiscoverActionDto,
  MediaStackDiscoverItemDto,
  MediaStackDiscoverRequestPayload,
  MediaStackExternalDiscoverDto,
  MediaStackExternalDiscoverItemDto,
  MediaStackHermesDiscoverDto,
  MediaStackLibraryItemDto,
  MediaStackTorrentDto,
  TraktDiscoverType,
} from './media-stack-api';

const DEMO_TORRENTS: MediaStackTorrentDto[] = [
  { hash: 'demo-afterlight', name: 'Afterlight', state: 'downloading', progress: 0.68, size: 7_400_000_000, downloaded: 5_032_000_000, dlspeed: 4_200_000, upspeed: 320_000, eta: 540, category: 'Movies' },
  { hash: 'demo-blue-hour', name: 'The Blue Hour', state: 'downloading', progress: 0.31, size: 2_100_000_000, downloaded: 651_000_000, dlspeed: 1_800_000, upspeed: 80_000, eta: 800, category: 'TV' },
  { hash: 'demo-orbit', name: 'Orbit Station', state: 'stoppedUP', progress: 1, size: 5_800_000_000, downloaded: 5_800_000_000, dlspeed: 0, upspeed: 120_000, eta: 0, category: 'Movies' },
];

const DEMO_CALENDAR: MediaStackCalendarEventDto[] = [
  {
    title: 'Cowboy Bebop',
    additional: 'S1 E5',
    date: 'Jul 12',
    airDate: '2026-07-12T18:00:00Z',
    hasFile: false,
    kind: 'episode',
  },
  {
    title: 'The Blue Hour',
    additional: 'S2 E3',
    date: 'Jul 12',
    airDate: '2026-07-12T21:30:00Z',
    hasFile: false,
    kind: 'episode',
  },
  {
    title: 'Dune',
    additional: 'Theatrical',
    date: 'Jul 13',
    airDate: '2026-07-13T00:00:00Z',
    hasFile: true,
    kind: 'movie',
  },
  {
    title: 'The Expanse',
    additional: 'S4 E2',
    date: 'Jul 14',
    airDate: '2026-07-14T21:00:00Z',
    hasFile: false,
    kind: 'episode',
  },
  {
    title: 'Night Transit',
    additional: 'Premiere',
    date: 'Jul 15',
    airDate: '2026-07-15T12:00:00Z',
    hasFile: false,
    kind: 'movie',
  },
];

const DEMO_LIBRARY: MediaStackArrLibraryDto = {
  ok: true,
  series: {
    'cowboy bebop': 'cowboy-bebop',
    'the expanse': 'the-expanse',
  },
  movies: {
    dune: 'dune-2021',
  },
};

const DEMO_LIBRARY_ITEMS: MediaStackLibraryItemDto[] = [
  {
    id: 'jf-dune',
    title: 'Dune',
    kind: 'movie',
    year: 2021,
    overview: 'A mythic desert world and the fight for its spice.',
    posterUrl: 'linear-gradient(145deg, #8b5a2b, #1a1410 70%)',
    playable: true,
  },
  {
    id: 'jf-afterlight',
    title: 'Afterlight',
    kind: 'movie',
    year: 2026,
    overview: 'A crew races the last light across a dying colony.',
    posterUrl: 'linear-gradient(145deg, #3d5a80, #0d1117 70%)',
    playable: true,
  },
  {
    id: 'jf-orbit',
    title: 'Orbit Station',
    kind: 'movie',
    year: 2024,
    overview: 'Docking bay politics at the edge of settled space.',
    posterUrl: 'linear-gradient(145deg, #4a5568, #111827 70%)',
    playable: true,
  },
  {
    id: 'jf-night-transit',
    title: 'Night Transit',
    kind: 'movie',
    year: 2026,
    overview: 'A premiere without artwork in the demo catalog.',
    artworkState: 'missing',
    playable: true,
  },
  {
    id: 'jf-cowboy-bebop',
    title: 'Cowboy Bebop',
    kind: 'series',
    year: 1998,
    overview: 'Bounty hunters chasing the past across the solar system.',
    posterUrl: 'linear-gradient(145deg, #b45309, #1c1917 70%)',
    playable: true,
  },
  {
    id: 'jf-the-expanse',
    title: 'The Expanse',
    kind: 'series',
    year: 2015,
    overview: 'Politics and survival between Earth, Mars, and the Belt.',
    posterUrl: 'linear-gradient(145deg, #1e3a5f, #0b1220 70%)',
    playable: true,
  },
  {
    id: 'jf-blue-hour',
    title: 'The Blue Hour',
    kind: 'series',
    year: 2023,
    overview: 'Late-night cases in a city that never fully wakes.',
    posterUrl: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
    playable: true,
  },
  {
    id: 'jf-broken-art',
    title: 'Broken Signal',
    kind: 'series',
    year: 2022,
    overview: 'Demo item with intentionally failed artwork.',
    posterUrl: 'http://example.invalid/broken-poster.jpg',
    artworkState: 'failed',
    playable: true,
  },
];

const DEMO_AUTOMATION_SUMMARY: MediaStackAutomationSummaryDto = {
  generatedAt: '2026-07-12T18:00:00Z',
  services: [
    { id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'Indexers reachable' },
    { id: 'radarr', name: 'Radarr', status: 'healthy', detail: 'Indexers reachable' },
    { id: 'prowlarr', name: 'Prowlarr', status: 'degraded', detail: 'One indexer slow to respond' },
    { id: 'sabnzbd', name: 'SABnzbd', status: 'down', detail: 'Connection refused' },
  ],
  preview: [
    { id: 'preview-1', title: 'Dune: Part Two', when: 'Tonight', kind: 'movie' },
    { id: 'preview-2', title: 'The Expanse S4 E2', when: 'Tomorrow', kind: 'episode' },
    { id: 'preview-3', title: 'Night Transit', when: 'Jul 15', kind: 'movie' },
  ],
  problems: [
    { id: 'problem-1', summary: 'SABnzbd unreachable', serviceId: 'sabnzbd', severity: 'actionable' },
    { id: 'problem-2', summary: 'Prowlarr indexer response slow', serviceId: 'prowlarr', severity: 'warning' },
  ],
};

const PARTIAL_AUTOMATION_SUMMARY: MediaStackAutomationSummaryDto = {
  generatedAt: '2026-07-12T18:00:00Z',
  services: [
    { id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK' },
  ],
  preview: [],
  unavailable: { preview: true, problems: true },
};

const DEMO_CRON_LOGS: MediaStackCronLogsDto = {
  ok: true,
  generatedAt: '2026-07-12T12:00:00Z',
  logs: [
    {
      id: 'watchdog',
      title: 'Watchdog',
      file: 'watchdog.ndjson',
      format: 'ndjson',
      schedule: '*/15 * * * *',
      description: 'Stack health and disk checks',
      exists: true,
      size: 4200,
      mtime: '2026-07-12T11:45:00Z',
      lastStatus: 'fatal',
      runs: [
        {
          timestamp: '2026-07-12T11:45:00Z',
          status: 'fatal',
          detail: 'Disk usage critical on /data',
          fatal: 'Disk usage critical on /data',
          exitCode: 1,
        },
        {
          timestamp: '2026-07-12T11:30:00Z',
          status: 'ok',
          detail: 'Checked 4, no repairs needed',
          exitCode: 0,
        },
      ],
    },
    {
      id: 'stale-metadata',
      title: 'Stale metadata',
      file: 'stale-metadata.ndjson',
      format: 'ndjson',
      schedule: '0 */6 * * *',
      description: 'Repair stale Sonarr/Radarr metadata',
      exists: true,
      size: 3100,
      mtime: '2026-07-12T10:00:00Z',
      lastStatus: 'warn',
      runs: [
        {
          timestamp: '2026-07-12T10:00:00Z',
          status: 'warn',
          detail: '3 stale entries need review',
          exitCode: 0,
        },
        {
          timestamp: '2026-07-12T04:00:00Z',
          status: 'ok',
          detail: 'Nothing to check',
          exitCode: 0,
        },
      ],
    },
    {
      id: 'hardlink-cleanup',
      title: 'Hardlink cleanup',
      file: 'hardlink-cleanup.ndjson',
      format: 'ndjson',
      schedule: '30 3 * * *',
      description: 'Reclaim space from orphaned hardlinks',
      exists: true,
      size: 2800,
      mtime: '2026-07-12T03:30:00Z',
      lastStatus: 'applied',
      runs: [
        {
          timestamp: '2026-07-12T03:30:00Z',
          status: 'applied',
          detail: 'Applied 2 repairs',
          applied: 2,
          evaluated: 18,
          skipped: 0,
          exitCode: 0,
        },
      ],
    },
    {
      id: 'weekly-validate',
      title: 'Weekly validate',
      file: 'weekly-validate.log',
      format: 'text',
      schedule: '0 4 * * 0',
      description: 'Weekly library integrity pass',
      exists: true,
      size: 1200,
      mtime: '2026-07-06T04:00:00Z',
      lastStatus: 'ok',
      runs: [
        {
          timestamp: '2026-07-06T04:00:00Z',
          status: 'ok',
          detail: 'Completed',
          exitCode: 0,
        },
      ],
    },
  ],
};

function copyCronLogs(source: MediaStackCronLogsDto): MediaStackCronLogsDto {
  return {
    ...source,
    logs: source.logs.map(
      (entry): MediaStackCronLogEntryDto => ({
        ...entry,
        actions: entry.actions ? [...entry.actions] : undefined,
        runs: entry.runs?.map((run) => ({
          ...run,
          highlights: run.highlights ? [...run.highlights] : undefined,
        })),
      }),
    ),
  };
}

export type AutomationScenario = 'default' | 'partial' | 'empty';

const DEMO_HERMES: MediaStackDiscoverItemDto[] = [
  {
    id: 'hermes-eligible',
    source: 'hermes',
    type: 'movie',
    title: 'Signal Drift',
    year: 2024,
    tmdb_id: 101001,
    reason: 'Matches your sci-fi taste',
    active: true,
    feedback: null,
    feedback_at: null,
    request_state: null,
    requested_at: null,
    jellyseerr_request_id: null,
    in_library: false,
    poster_url: null,
    added_at: '2026-07-10T12:00:00Z',
  },
  {
    id: 'hermes-in-library',
    source: 'hermes',
    type: 'tv',
    title: 'Harbor Lights',
    year: 2023,
    tmdb_id: 101002,
    reason: 'Serialized drama you already own',
    active: true,
    feedback: null,
    feedback_at: null,
    request_state: null,
    requested_at: null,
    jellyseerr_request_id: null,
    in_library: true,
    jellyfin_id: 'jf-harbor',
    poster_url: null,
    added_at: '2026-07-10T12:05:00Z',
  },
  {
    id: 'hermes-requested',
    source: 'hermes',
    type: 'movie',
    title: 'Glass Atlas',
    year: 2025,
    tmdb_id: 101003,
    reason: 'Already requested earlier',
    active: true,
    feedback: null,
    feedback_at: null,
    request_state: 'requested',
    requested_at: '2026-07-09T09:00:00Z',
    jellyseerr_request_id: 9001,
    in_library: false,
    poster_url: null,
    added_at: '2026-07-08T12:00:00Z',
  },
  {
    id: 'hermes-no-tmdb',
    source: 'hermes',
    type: 'movie',
    title: 'Untitled Cut',
    year: null,
    tmdb_id: 0,
    reason: 'Missing catalog identity',
    active: true,
    feedback: null,
    feedback_at: null,
    request_state: null,
    requested_at: null,
    jellyseerr_request_id: null,
    in_library: false,
    poster_url: null,
    added_at: '2026-07-10T13:00:00Z',
  },
  {
    id: 'hermes-sync-failed',
    source: 'hermes',
    type: 'tv',
    title: 'Night Courier',
    year: 2022,
    tmdb_id: 101005,
    reason: 'Eligible until a sync-failed request',
    active: true,
    feedback: null,
    feedback_at: null,
    request_state: null,
    requested_at: null,
    jellyseerr_request_id: null,
    in_library: false,
    poster_url: null,
    added_at: '2026-07-10T14:00:00Z',
  },
  {
    id: 'hermes-history-liked',
    source: 'hermes',
    type: 'movie',
    title: 'Copper Skies',
    year: 2021,
    tmdb_id: 201001,
    active: false,
    feedback: 'liked',
    feedback_at: '2026-07-01T10:00:00Z',
    request_state: null,
    requested_at: null,
    jellyseerr_request_id: null,
    in_library: false,
    poster_url: null,
    added_at: '2026-06-20T12:00:00Z',
  },
  {
    id: 'hermes-history-watched',
    source: 'hermes',
    type: 'tv',
    title: 'River Protocol',
    year: 2020,
    tmdb_id: 201002,
    active: false,
    feedback: 'watched',
    feedback_at: '2026-07-02T10:00:00Z',
    request_state: null,
    requested_at: null,
    jellyseerr_request_id: null,
    in_library: true,
    poster_url: null,
    added_at: '2026-06-21T12:00:00Z',
  },
  {
    id: 'hermes-history-disliked',
    source: 'hermes',
    type: 'movie',
    title: 'Static Bloom',
    year: 2019,
    tmdb_id: 201003,
    active: false,
    feedback: 'disliked',
    feedback_at: '2026-07-03T10:00:00Z',
    request_state: null,
    requested_at: null,
    jellyseerr_request_id: null,
    in_library: false,
    poster_url: null,
    added_at: '2026-06-22T12:00:00Z',
  },
  {
    id: 'hermes-history-skipped',
    source: 'hermes',
    type: 'tv',
    title: 'Quiet Frequency',
    year: 2018,
    tmdb_id: 201004,
    active: false,
    feedback: 'skipped',
    feedback_at: '2026-07-04T10:00:00Z',
    request_state: 'requested',
    requested_at: '2026-07-04T11:00:00Z',
    jellyseerr_request_id: 9002,
    in_library: false,
    poster_url: null,
    added_at: '2026-06-23T12:00:00Z',
  },
];

const DEMO_JELLYSEERR: Record<JellyseerrDiscoverKind, MediaStackExternalDiscoverItemDto[]> = {
  trending: [
    { id: 'js-trending-1', source: 'jellyseerr', type: 'movie', title: 'Trending Ember', year: 2026, tmdb_id: 301001, overview: 'Jellyseerr trending movie' },
    { id: 'js-trending-2', source: 'jellyseerr', type: 'tv', title: 'Trending Tide', year: 2025, tmdb_id: 301002, overview: 'Jellyseerr trending show' },
  ],
  movies: [
    { id: 'js-movies-1', source: 'jellyseerr', type: 'movie', title: 'Neon Archive', year: 2024, tmdb_id: 302001, overview: 'Jellyseerr movies feed' },
    { id: 'js-movies-2', source: 'jellyseerr', type: 'movie', title: 'Paper Orbit', year: 2023, tmdb_id: 302002, overview: 'Jellyseerr movies feed' },
  ],
  tv: [
    { id: 'js-tv-1', source: 'jellyseerr', type: 'tv', title: 'Channel Zero Point', year: 2024, tmdb_id: 303001, overview: 'Jellyseerr tv feed' },
    { id: 'js-tv-2', source: 'jellyseerr', type: 'tv', title: 'Late Broadcast', year: 2022, tmdb_id: 303002, overview: 'Jellyseerr tv feed' },
  ],
};

const DEMO_TRAKT: Record<TraktDiscoverType, MediaStackExternalDiscoverItemDto[]> = {
  movies: [
    { id: 'trakt-movies-1', source: 'trakt', type: 'movie', title: 'Trakt Horizon', year: 2025, tmdb_id: 401001, overview: 'Trakt movies feed' },
    { id: 'trakt-movies-2', source: 'trakt', type: 'movie', title: 'Trakt Meridian', year: 2024, tmdb_id: 401002, overview: 'Trakt movies feed' },
  ],
  shows: [
    { id: 'trakt-shows-1', source: 'trakt', type: 'tv', title: 'Trakt Relay', year: 2025, tmdb_id: 402001, overview: 'Trakt shows feed' },
    { id: 'trakt-shows-2', source: 'trakt', type: 'tv', title: 'Trakt Cascade', year: 2023, tmdb_id: 402002, overview: 'Trakt shows feed' },
  ],
};

/** Fixture id that simulates dashboard_state_persisted: false on request. */
export const MOCK_SYNC_FAILED_HERMES_ID = 'hermes-sync-failed';

@Injectable()
export class MockMediaStackApi implements MediaStackApi {
  private torrents = DEMO_TORRENTS.map((torrent) => ({ ...torrent }));
  private calendar = DEMO_CALENDAR.map((event) => ({ ...event }));
  private library: MediaStackArrLibraryDto = {
    ok: DEMO_LIBRARY.ok,
    series: { ...DEMO_LIBRARY.series },
    movies: { ...DEMO_LIBRARY.movies },
  };
  private hermesItems = DEMO_HERMES.map((item) => ({ ...item }));
  private hermesMorePending = false;
  private hermesMoreRequestedAt: string | null = null;
  private nextJellyseerrRequestId = 9100;
  private requestedKeys = new Set<string>();
  private libraryItems = DEMO_LIBRARY_ITEMS.map((item) => ({ ...item }));
  private cronLogs = copyCronLogs(DEMO_CRON_LOGS);
  private automationScenario: AutomationScenario = 'default';

  setAutomationScenario(scenario: AutomationScenario): void {
    this.automationScenario = scenario;
  }

  listTorrents(): Promise<MediaStackTorrentDto[]> {
    return Promise.resolve(this.torrents.map((torrent) => ({ ...torrent })));
  }

  pauseAll(): Promise<void> {
    this.torrents = this.torrents.map((torrent) => ({ ...torrent, state: 'paused', dlspeed: 0, upspeed: 0 }));
    return Promise.resolve();
  }

  resumeAll(): Promise<void> {
    this.torrents = this.torrents.map((torrent) => {
      const demo = DEMO_TORRENTS.find((demoTorrent) => demoTorrent.hash === torrent.hash);
      return {
        ...torrent,
        state: torrent.progress >= 1 ? 'stoppedUP' : 'downloading',
        dlspeed: demo?.dlspeed ?? 0,
        upspeed: demo?.upspeed ?? 0,
      };
    });
    return Promise.resolve();
  }

  listCalendarEvents(): Promise<MediaStackCalendarEventDto[]> {
    const events = this.calendar
      .map((event) => ({ ...event }))
      .sort((left, right) => (left.airDate ?? '').localeCompare(right.airDate ?? ''));
    return Promise.resolve(events);
  }

  getArrLibrary(): Promise<MediaStackArrLibraryDto> {
    return Promise.resolve({
      ok: this.library.ok,
      series: { ...this.library.series },
      movies: { ...this.library.movies },
    });
  }


  listLibraryItems(filter?: { kind?: LibraryItemKind }): Promise<MediaStackLibraryItemDto[]> {
    const items = this.libraryItems
      .filter((item) => !filter?.kind || item.kind === filter.kind)
      .map((item) => ({ ...item }));
    return Promise.resolve(items);
  }

  getAutomationSummary(): Promise<MediaStackAutomationSummaryDto> {
    const summary =
      this.automationScenario === 'partial'
        ? PARTIAL_AUTOMATION_SUMMARY
        : this.automationScenario === 'empty'
          ? { generatedAt: '2026-07-12T18:00:00Z', services: [], preview: [], problems: [] }
          : DEMO_AUTOMATION_SUMMARY;
    return Promise.resolve(structuredClone(summary));
  }
  listCronLogs(): Promise<MediaStackCronLogsDto> {
    return Promise.resolve(copyCronLogs(this.cronLogs));
  }


  listHermesRecommendations(): Promise<MediaStackHermesDiscoverDto> {
    const pending_request_sync = this.hermesItems
      .filter((item) => item.id === MOCK_SYNC_FAILED_HERMES_ID && item.jellyseerr_request_id && item.request_state == null)
      .map((item) => ({ id: item.id, jellyseerr_request_id: item.jellyseerr_request_id as number }));
    return Promise.resolve({
      ok: true,
      items: this.hermesItems.map((item) => ({ ...item })),
      pending_request_sync,
      generation_request: this.hermesMorePending && this.hermesMoreRequestedAt
        ? { requested_at: this.hermesMoreRequestedAt, status: 'pending' }
        : null,
    });
  }

  submitHermesFeedback(id: string, feedback: DiscoverFeedback, notes?: string): Promise<MediaStackDiscoverActionDto> {
    const item = this.hermesItems.find((candidate) => candidate.id === id);
    if (!item) {
      return Promise.resolve({ ok: false, error: 'Recommendation not found' });
    }
    item.feedback = feedback;
    item.feedback_at = new Date().toISOString();
    item.active = false;
    if (notes !== undefined) {
      item.notes = notes;
    }
    return Promise.resolve({ ok: true, message: 'Feedback saved' });
  }

  requestHermesMore(): Promise<MediaStackDiscoverActionDto> {
    if (this.hermesMorePending) {
      return Promise.resolve({
        ok: true,
        already_pending: true,
        queued: false,
        message: 'A recommendation refresh is already pending',
        requested_at: this.hermesMoreRequestedAt ?? undefined,
      });
    }
    this.hermesMorePending = true;
    this.hermesMoreRequestedAt = new Date().toISOString();
    return Promise.resolve({
      ok: true,
      queued: true,
      already_pending: false,
      message: 'More recommendations queued',
      requested_at: this.hermesMoreRequestedAt,
    });
  }

  listJellyseerrDiscover(kind: JellyseerrDiscoverKind): Promise<MediaStackExternalDiscoverDto> {
    return Promise.resolve({
      ok: true,
      items: (DEMO_JELLYSEERR[kind] ?? []).map((item) => ({ ...item })),
    });
  }

  listTraktDiscover(type: TraktDiscoverType): Promise<MediaStackExternalDiscoverDto> {
    return Promise.resolve({
      ok: true,
      items: (DEMO_TRAKT[type] ?? []).map((item) => ({ ...item })),
    });
  }

  requestMedia(payload: MediaStackDiscoverRequestPayload): Promise<MediaStackDiscoverActionDto> {
    if (!payload.mediaId) {
      return Promise.resolve({ ok: false, error: 'Cannot request — missing TMDB id' });
    }

    const identityKey = `${payload.mediaType}:${payload.mediaId}`;
    const hermesItem = payload.hermesId
      ? this.hermesItems.find((item) => item.id === payload.hermesId)
      : this.hermesItems.find(
          (item) => item.tmdb_id === payload.mediaId && item.type === payload.mediaType,
        );

    if (hermesItem?.request_state === 'requested' || this.requestedKeys.has(identityKey)) {
      return Promise.resolve({
        ok: true,
        message: 'Already requested',
        jellyseerr_request_id: hermesItem?.jellyseerr_request_id ?? null,
        dashboard_state_persisted: true,
      });
    }

    const requestId = this.nextJellyseerrRequestId++;
    const requestedAt = new Date().toISOString();
    const syncFailed = hermesItem?.id === MOCK_SYNC_FAILED_HERMES_ID;

    if (hermesItem) {
      if (syncFailed) {
        // Arr accepted the request but dashboard state did not persist — leave request_state null.
        hermesItem.jellyseerr_request_id = requestId;
        return Promise.resolve({
          ok: true,
          partial_success: true,
          jellyseerr_request_id: requestId,
          dashboard_state_persisted: false,
          reconciliation_queued: true,
          message: 'Added to Sonarr/Radarr; dashboard synchronization failed.',
          requested_at: requestedAt,
        });
      }
      hermesItem.request_state = 'requested';
      hermesItem.requested_at = requestedAt;
      hermesItem.jellyseerr_request_id = requestId;
    }

    this.requestedKeys.add(identityKey);

    return Promise.resolve({
      ok: true,
      jellyseerr_request_id: requestId,
      dashboard_state_persisted: true,
      message: 'Requested',
      requested_at: requestedAt,
    });
  }

  /** Test helper: clear generation pending so request-more can queue again. */
  resetHermesMorePending(): void {
    this.hermesMorePending = false;
    this.hermesMoreRequestedAt = null;
  }
}
