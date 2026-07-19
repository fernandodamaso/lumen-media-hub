import { Injectable } from '@angular/core';

import { ArrLibrary, CalendarEvent } from '../calendar/calendar.models';
import {
  DiscoverAction,
  DiscoverFeedback,
  DiscoverRequestPayload,
  ExternalDiscover,
  HermesDiscover,
  JellyseerrDiscoverKind,
  TraktDiscoverType,
} from '../discover/discover.models';
import { DownloadTorrent } from '../downloads/downloads.models';
import { LibraryItem, LibraryItemKind, LibraryListResult, LibraryStats } from '../library/library.models';
import { AutomationSummary } from '../automation/automation.models';
import { CronLogs } from '../reports/reports.models';
import { StorageOverview } from '../storage/storage.models';
import { MediaStackApi } from './media-stack-api';
import { mapArrLibrary, mapCalendarEvent } from '../calendar/calendar-format';
import { mapAutomationSummary } from '../automation/automation-format';
import { mapCronLogs } from '../reports/reports-format';
import {
  mapDiscoverAction,
  mapExternalDiscover,
  mapHermesDiscover,
} from '../discover/discover-format';
import { mapLibraryItem, mapLibraryStats } from '../library/library-format';
import { mapTorrent } from '../downloads/downloads-format';
import { mapStorageOverview } from '../storage/storage-format';
import { MediaStackArrLibraryDto, MediaStackCalendarEventDto } from './wire/calendar';
import { MediaStackAutomationSummaryDto } from './wire/automation';
import { MediaStackCronLogEntryDto, MediaStackCronLogsDto } from './wire/cron';
import {
  MediaStackDiscoverItemDto,
  MediaStackExternalDiscoverItemDto,
} from './wire/discover';
import { MediaStackLibraryItemDto, MediaStackLibraryStatsDto } from './wire/library';
import { MediaStackStorageOverviewDto } from './wire/storage';
import { MediaStackTorrentDto } from './wire/torrents';

const KIB = 1024;
const MIB = 1024 * KIB;
const GIB = 1024 * MIB;
const TIB = 1024 * GIB;

const DEMO_TORRENTS: MediaStackTorrentDto[] = [
  { hash: 'demo-afterlight', name: 'Afterlight', state: 'downloading', progress: 0.68, size: Math.round(6.9 * GIB), downloaded: Math.round(4.7 * GIB), dlspeed: Math.round(4.0 * MIB), upspeed: 312 * KIB, eta: 9 * 60, category: 'Movies' },
  { hash: 'demo-blue-hour', name: 'The Blue Hour', state: 'downloading', progress: 0.31, size: 2 * GIB, downloaded: 620 * MIB, dlspeed: Math.round(1.7 * MIB), upspeed: 78 * KIB, eta: 13 * 60, category: 'TV · S2E3' },
  { hash: 'demo-orbit', name: 'Orbit Station', state: 'stoppedUP', progress: 1, size: Math.round(5.4 * GIB), downloaded: Math.round(5.4 * GIB), dlspeed: 0, upspeed: 117 * KIB, eta: 0, category: 'Movies' },
];

const DEMO_LIBRARY_STATS: MediaStackLibraryStatsDto = { ok: true, movies: 428, series: 76 };

function demoStorageOverview(): MediaStackStorageOverviewDto {
  return {
    ok: true,
    generatedAt: new Date().toISOString(),
    volumes: [
      { id: 'media-library', label: 'Media library', kind: 'library', usedBytes: Math.round(4.8 * TIB), totalBytes: Math.round(7.2 * TIB) },
      { id: 'downloads', label: 'Downloads', kind: 'downloads', usedBytes: 324 * GIB, totalBytes: TIB },
      { id: 'cache', label: 'Cache & temp', kind: 'cache', usedBytes: 68 * GIB, totalBytes: 500 * GIB },
    ],
  };
}

/** Demo calendar is relative to now so TODAY/TOMORROW groups stay meaningful. */
function demoCalendar(now = new Date()): MediaStackCalendarEventDto[] {
  const pad = (value: number): string => String(value).padStart(2, '0');
  const stamp = (dayOffset: number, hours: number, minutes: number) => {
    const date = new Date(now.getFullYear(), now.getMonth(), now.getDate() + dayOffset, hours, minutes);
    return { airDate: date.toISOString(), date: `${pad(hours)}:${pad(minutes)}` };
  };
  const bebop = stamp(0, 18, 0);
  const blueHour = stamp(0, 21, 30);
  const dune = stamp(1, 0, 0);
  const expanse = stamp(3, 21, 0);
  return [
    {
      title: 'Cowboy Bebop',
      additional: 'S1 E5',
      date: bebop.date,
      airDate: bebop.airDate,
      hasFile: true,
      kind: 'episode',
      art: 'linear-gradient(145deg, #b45309, #1c1917 70%)',
    },
    {
      title: 'The Blue Hour',
      additional: 'S2 E3',
      date: blueHour.date,
      airDate: blueHour.airDate,
      monitored: true,
      kind: 'episode',
      art: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
    },
    {
      title: 'Dune',
      additional: 'Movie · Premiere',
      date: dune.date,
      airDate: dune.airDate,
      premiere: true,
      kind: 'movie',
      art: 'linear-gradient(145deg, #8b5a2b, #1a1410 70%)',
    },
    {
      title: 'The Expanse',
      additional: 'S4 E2',
      date: expanse.date,
      airDate: expanse.airDate,
      monitored: true,
      kind: 'episode',
      art: 'linear-gradient(145deg, #1e3a5f, #0b1220 70%)',
    },
  ];
}

const DEMO_LIBRARY: MediaStackArrLibraryDto = {
  ok: true,
  series: {
    'cowboy bebop': 'cowboy-bebop',
    'the blue hour': 'the-blue-hour',
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

function demoAutomationSummary(): MediaStackAutomationSummaryDto {
  return {
    generatedAt: new Date().toISOString(),
    services: [
      { id: 'jellyfin', name: 'Jellyfin', status: 'healthy', detail: 'Streaming ready', latencyMs: 18 },
      { id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'Indexers reachable', latencyMs: 20 },
      { id: 'radarr', name: 'Radarr', status: 'healthy', detail: 'Indexers reachable', latencyMs: 22 },
      { id: 'prowlarr', name: 'Prowlarr', status: 'degraded', detail: 'One indexer slow to respond', latencyMs: 350 },
      { id: 'sabnzbd', name: 'SABnzbd', status: 'down', detail: 'Last seen 18m ago' },
      { id: 'qbittorrent', name: 'qBittorrent', status: 'healthy', detail: 'Connected', latencyMs: 15 },
      { id: 'bazarr', name: 'Bazarr', status: 'healthy', detail: 'Subtitles up to date', latencyMs: 16 },
      { id: 'unpackerr', name: 'Unpackerr', status: 'healthy', detail: 'Queue empty', latencyMs: 24 },
    ],
    preview: [
      { id: 'preview-1', title: 'Cowboy Bebop S1 E5', when: 'Tonight', kind: 'episode' },
      { id: 'preview-2', title: 'Dune', when: 'Tomorrow', kind: 'movie' },
      { id: 'preview-3', title: 'The Expanse S4 E2', when: 'This week', kind: 'episode' },
    ],
    problems: [
      { id: 'problem-1', summary: 'SABnzbd unreachable', serviceId: 'sabnzbd', severity: 'actionable' },
      { id: 'problem-2', summary: 'Prowlarr indexer response slow', serviceId: 'prowlarr', severity: 'warning' },
      { id: 'problem-3', summary: 'Prowlarr indexer in cooldown', serviceId: 'prowlarr', severity: 'warning' },
    ],
  };
}

const PARTIAL_AUTOMATION_SUMMARY: MediaStackAutomationSummaryDto = {
  generatedAt: '2026-07-12T18:00:00Z',
  services: [
    { id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK' },
  ],
  preview: [],
  unavailable: { preview: true, problems: true },
};

/** Demo cron runs are relative to now so the dashboard "xm ago" column stays fresh. */
function demoCronLogs(now = Date.now()): MediaStackCronLogsDto {
  const ago = (minutes: number): string => new Date(now - minutes * 60_000).toISOString();
  return {
    ok: true,
    generatedAt: new Date(now).toISOString(),
    logs: [
      {
        id: 'hardlink-cleanup',
        title: 'Hardlink cleanup',
        file: 'hardlink-cleanup.ndjson',
        format: 'ndjson',
        schedule: '30 3 * * *',
        description: 'Reclaim space from orphaned hardlinks',
        exists: true,
        size: 2800,
        mtime: ago(3),
        lastStatus: 'applied',
        runs: [
          {
            timestamp: ago(3),
            status: 'applied',
            detail: '42 files hardlinked, 18.7 GB saved',
            applied: 42,
            evaluated: 214,
            skipped: 0,
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
        mtime: ago(18),
        lastStatus: 'fatal',
        runs: [
          {
            timestamp: ago(18),
            status: 'fatal',
            detail: '3 items failed to refresh',
            fatal: '3 items failed to refresh',
            exitCode: 1,
          },
        ],
      },
      {
        id: 'watchdog',
        title: 'Watchdog',
        file: 'watchdog.ndjson',
        format: 'ndjson',
        schedule: '*/15 * * * *',
        description: 'Stack health and disk checks',
        exists: true,
        size: 4200,
        mtime: ago(35),
        lastStatus: 'ok',
        runs: [
          {
            timestamp: ago(35),
            status: 'ok',
            detail: 'All services are healthy',
            exitCode: 0,
          },
        ],
      },
    ],
  };
}

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
  private automationScenario: AutomationScenario = 'default';

  setAutomationScenario(scenario: AutomationScenario): void {
    this.automationScenario = scenario;
  }

  listTorrents(_signal?: AbortSignal): Promise<DownloadTorrent[]> {
    return Promise.resolve(this.torrents.map((torrent) => mapTorrent({ ...torrent })));
  }

  pauseAll(): Promise<void> {
    this.torrents = this.torrents.map((torrent) => ({ ...torrent, state: 'paused', dlspeed: 0, upspeed: 0 }));
    return Promise.resolve();
  }

  resumeAll(): Promise<void> {
    this.torrents = this.torrents.map((torrent) => this.resumeTorrentDto(torrent));
    return Promise.resolve();
  }

  pauseTorrent(id: string): Promise<void> {
    this.torrents = this.torrents.map((torrent) =>
      torrent.hash === id ? { ...torrent, state: 'paused', dlspeed: 0, upspeed: 0 } : torrent,
    );
    return Promise.resolve();
  }

  resumeTorrent(id: string): Promise<void> {
    this.torrents = this.torrents.map((torrent) =>
      torrent.hash === id ? this.resumeTorrentDto(torrent) : torrent,
    );
    return Promise.resolve();
  }

  private resumeTorrentDto(torrent: MediaStackTorrentDto): MediaStackTorrentDto {
    const demo = DEMO_TORRENTS.find((demoTorrent) => demoTorrent.hash === torrent.hash);
    return {
      ...torrent,
      state: torrent.progress >= 1 ? 'stoppedUP' : 'downloading',
      dlspeed: demo?.dlspeed ?? 0,
      upspeed: demo?.upspeed ?? 0,
    };
  }

  listCalendarEvents(_signal?: AbortSignal): Promise<CalendarEvent[]> {
    const events = demoCalendar()
      .sort((left, right) => (left.airDate ?? '').localeCompare(right.airDate ?? ''))
      .map(mapCalendarEvent);
    return Promise.resolve(events);
  }

  getArrLibrary(_signal?: AbortSignal): Promise<ArrLibrary> {
    return Promise.resolve(
      mapArrLibrary({
        ok: this.library.ok,
        series: { ...this.library.series },
        movies: { ...this.library.movies },
      }),
    );
  }

  listLibraryItems(filter?: { kind?: LibraryItemKind }, _signal?: AbortSignal): Promise<LibraryListResult> {
    const items = this.libraryItems
      .filter((item) => !filter?.kind || item.kind === filter.kind)
      .map((item) => mapLibraryItem({ ...item }))
      .filter((item): item is LibraryItem => item !== null);
    return Promise.resolve({ items, availability: 'complete' });
  }

  getLibraryStats(_signal?: AbortSignal): Promise<LibraryStats> {
    return Promise.resolve(mapLibraryStats({ ...DEMO_LIBRARY_STATS }));
  }

  getStorageOverview(_signal?: AbortSignal): Promise<StorageOverview> {
    return Promise.resolve(mapStorageOverview(demoStorageOverview()));
  }

  getAutomationSummary(_signal?: AbortSignal): Promise<AutomationSummary> {
    const summary =
      this.automationScenario === 'partial'
        ? PARTIAL_AUTOMATION_SUMMARY
        : this.automationScenario === 'empty'
          ? { generatedAt: new Date().toISOString(), services: [], preview: [], problems: [] }
          : demoAutomationSummary();
    return Promise.resolve(mapAutomationSummary(structuredClone(summary)));
  }

  listCronLogs(_signal?: AbortSignal): Promise<CronLogs> {
    return Promise.resolve(mapCronLogs(copyCronLogs(demoCronLogs())));
  }

  listHermesRecommendations(): Promise<HermesDiscover> {
    const pending_request_sync = this.hermesItems
      .filter((item) => item.id === MOCK_SYNC_FAILED_HERMES_ID && item.jellyseerr_request_id && item.request_state == null)
      .map((item) => ({ id: item.id, jellyseerr_request_id: item.jellyseerr_request_id as number }));
    return Promise.resolve(
      mapHermesDiscover({
        ok: true,
        items: this.hermesItems.map((item) => ({ ...item })),
        pending_request_sync,
        generation_request: this.hermesMorePending && this.hermesMoreRequestedAt
          ? { requested_at: this.hermesMoreRequestedAt, status: 'pending' }
          : null,
      }),
    );
  }

  submitHermesFeedback(id: string, feedback: DiscoverFeedback, notes?: string): Promise<DiscoverAction> {
    const item = this.hermesItems.find((candidate) => candidate.id === id);
    if (!item) {
      return Promise.resolve(mapDiscoverAction({ ok: false, error: 'Recommendation not found' }));
    }
    item.feedback = feedback;
    item.feedback_at = new Date().toISOString();
    item.active = false;
    if (notes !== undefined) {
      item.notes = notes;
    }
    return Promise.resolve(mapDiscoverAction({ ok: true, message: 'Feedback saved' }));
  }

  requestHermesMore(): Promise<DiscoverAction> {
    if (this.hermesMorePending) {
      return Promise.resolve(
        mapDiscoverAction({
          ok: true,
          already_pending: true,
          queued: false,
          message: 'A recommendation refresh is already pending',
          requested_at: this.hermesMoreRequestedAt ?? undefined,
        }),
      );
    }
    this.hermesMorePending = true;
    this.hermesMoreRequestedAt = new Date().toISOString();
    return Promise.resolve(
      mapDiscoverAction({
        ok: true,
        queued: true,
        already_pending: false,
        message: 'More recommendations queued',
        requested_at: this.hermesMoreRequestedAt,
      }),
    );
  }

  listJellyseerrDiscover(kind: JellyseerrDiscoverKind): Promise<ExternalDiscover> {
    return Promise.resolve(
      mapExternalDiscover({
        ok: true,
        items: (DEMO_JELLYSEERR[kind] ?? []).map((item) => ({ ...item })),
      }),
    );
  }

  listTraktDiscover(type: TraktDiscoverType): Promise<ExternalDiscover> {
    return Promise.resolve(
      mapExternalDiscover({
        ok: true,
        items: (DEMO_TRAKT[type] ?? []).map((item) => ({ ...item })),
      }),
    );
  }

  requestMedia(payload: DiscoverRequestPayload): Promise<DiscoverAction> {
    if (!payload.mediaId) {
      return Promise.resolve(mapDiscoverAction({ ok: false, error: 'Cannot request — missing TMDB id' }));
    }

    const identityKey = `${payload.mediaType}:${payload.mediaId}`;
    const hermesItem = payload.hermesId
      ? this.hermesItems.find((item) => item.id === payload.hermesId)
      : this.hermesItems.find(
          (item) => item.tmdb_id === payload.mediaId && item.type === payload.mediaType,
        );

    if (hermesItem?.request_state === 'requested' || this.requestedKeys.has(identityKey)) {
      return Promise.resolve(
        mapDiscoverAction({
          ok: true,
          message: 'Already requested',
          jellyseerr_request_id: hermesItem?.jellyseerr_request_id ?? null,
          dashboard_state_persisted: true,
        }),
      );
    }

    const requestId = this.nextJellyseerrRequestId++;
    const requestedAt = new Date().toISOString();
    const syncFailed = hermesItem?.id === MOCK_SYNC_FAILED_HERMES_ID;

    if (hermesItem) {
      if (syncFailed) {
        // Arr accepted the request but dashboard state did not persist — leave request_state null.
        hermesItem.jellyseerr_request_id = requestId;
        return Promise.resolve(
          mapDiscoverAction({
            ok: true,
            partial_success: true,
            jellyseerr_request_id: requestId,
            dashboard_state_persisted: false,
            reconciliation_queued: true,
            message: 'Added to Sonarr/Radarr; dashboard synchronization failed.',
            requested_at: requestedAt,
          }),
        );
      }
      hermesItem.request_state = 'requested';
      hermesItem.requested_at = requestedAt;
      hermesItem.jellyseerr_request_id = requestId;
    }

    this.requestedKeys.add(identityKey);

    return Promise.resolve(
      mapDiscoverAction({
        ok: true,
        jellyseerr_request_id: requestId,
        dashboard_state_persisted: true,
        message: 'Requested',
        requested_at: requestedAt,
      }),
    );
  }

  /** Test helper: clear generation pending so request-more can queue again. */
  resetHermesMorePending(): void {
    this.hermesMorePending = false;
    this.hermesMoreRequestedAt = null;
  }
}
