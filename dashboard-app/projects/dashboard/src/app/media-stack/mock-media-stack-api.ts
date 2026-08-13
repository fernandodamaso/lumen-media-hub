import { Injectable } from '@angular/core';

import { ArrLibrary, CalendarEvent } from '../calendar/calendar.models';
import {
  DiscoverAction,
  DiscoverFeedback,
  DiscoverRequestPayload,
  ExternalDiscover,
  HermesDiscover,
  JellyseerrDiscoverKind,
  SubmitHermesFeedbackOptions,
  TraktDiscoverType,
} from '../discover/discover.models';
import { DownloadTorrent } from '../downloads/downloads.models';
import { LibraryItem, LibraryItemKind, LibraryDeletePreview, LibraryDeleteResult, LibraryListResult, LibraryStats } from '../library/library.models';
import { WatchNextResult } from '../library/watch-next.models';
import { RecentlyAvailableResult } from '../library/recently-available.models';
import { ActivityFeed } from '../activity/activity.models';
import { mapActivityFeed } from '../activity/activity-format';
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
import { mapWatchNextResult } from '../library/watch-next-format';
import { mapRecentlyAvailableResult } from '../library/recently-available-format';
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
import { MediaStackWatchNextItemDto } from './wire/watch-next';
import { MediaStackRecentlyAvailableItemDto } from './wire/recently-available';
import { MediaStackStorageOverviewDto } from './wire/storage';
import { MediaStackTorrentDto } from './wire/torrents';
import { MediaStackActivityFeedDto } from './wire/activity';

const KIB = 1024;
const MIB = 1024 * KIB;
const GIB = 1024 * MIB;
const TIB = 1024 * GIB;

const DEMO_TORRENTS: MediaStackTorrentDto[] = [
  { hash: 'demo-afterlight', name: 'Afterlight', state: 'downloading', progress: 0.68, size: Math.round(6.9 * GIB), downloaded: Math.round(4.7 * GIB), dlspeed: Math.round(4.0 * MIB), upspeed: 312 * KIB, eta: 9 * 60, category: 'Movies' },
  { hash: 'demo-blue-hour', name: 'The Blue Hour', state: 'downloading', progress: 0.31, size: 2 * GIB, downloaded: 620 * MIB, dlspeed: Math.round(1.7 * MIB), upspeed: 78 * KIB, eta: 13 * 60, category: 'TV · S2E3' },
  { hash: 'demo-orbit', name: 'Orbit Station', state: 'stalledUP', progress: 1, size: Math.round(5.4 * GIB), downloaded: Math.round(5.4 * GIB), dlspeed: 0, upspeed: 117 * KIB, eta: 0, category: 'Movies' },
];

const MIXED_TORRENTS: MediaStackTorrentDto[] = [
  { hash: 'demo-afterlight', name: 'Afterlight', state: 'downloading', progress: 0.68, size: Math.round(6.9 * GIB), downloaded: Math.round(4.7 * GIB), dlspeed: Math.round(4.0 * MIB), upspeed: 312 * KIB, eta: 9 * 60, category: 'Movies' },
  { hash: 'demo-orbit', name: 'Orbit Station', state: 'stalledUP', progress: 1, size: Math.round(5.4 * GIB), downloaded: Math.round(5.4 * GIB), dlspeed: 0, upspeed: 117 * KIB, eta: 0, category: 'Movies' },
  { hash: 'demo-silent-wave', name: 'Silent Wave', state: 'pausedDL', progress: 0.45, size: Math.round(3.2 * GIB), downloaded: Math.round(1.44 * GIB), dlspeed: 0, upspeed: 0, eta: 0, category: 'TV · S1E6' },
  { hash: 'demo-dust-road', name: 'Dust Road', state: 'queuedDL', progress: 0, size: Math.round(4.1 * GIB), downloaded: 0, dlspeed: 0, upspeed: 0, eta: 0, category: 'Movies' },
  { hash: 'demo-echo-point', name: 'Echo Point', state: 'checkingDL', progress: 0.92, size: Math.round(2.8 * GIB), downloaded: Math.round(2.8 * GIB), dlspeed: 0, upspeed: 0, eta: 0, category: 'TV · S3E1' },
  { hash: 'demo-broken-link', name: 'Broken Link', state: 'error', progress: 0.12, size: Math.round(6.1 * GIB), downloaded: Math.round(0.73 * GIB), dlspeed: 0, upspeed: 0, eta: 0, category: 'Movies' },
];

const DEMO_LIBRARY_STATS: MediaStackLibraryStatsDto = { ok: true, movies: 428, series: 76 };

const DEMO_WATCH_NEXT: MediaStackWatchNextItemDto[] = [
  {
    id: 'jf-expanse-s04e02',
    parentId: 'jf-expanse',
    title: 'The Expanse',
    subtitle: 'S04E02 · Jetsam',
    kind: 'episode',
    posterUrl: 'linear-gradient(145deg, #1e3a5f, #0b1220 70%)',
    playable: true,
    progressPercent: 42,
    year: 2015,
    rating: 8.3,
    genres: ['Sci-Fi', 'Adventure'],
    overview: 'Politics and survival between Earth, Mars, and the Belt.',
    runtimeTicks: 27_000_000_000,
    positionTicks: 11_340_000_000,
    backdropUrl: 'linear-gradient(160deg, #1e3a5f, #0b1220 60%)',
    thumbUrl: 'linear-gradient(160deg, #1e3a5f, #0b1220 60%)',
  },
  {
    id: 'jf-blue-hour-s02e03',
    parentId: 'jf-blue-hour',
    title: 'The Blue Hour',
    subtitle: 'S02E03 · Nightfall',
    kind: 'episode',
    posterUrl: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
    playable: true,
    progressPercent: 0,
    year: 2023,
    rating: 7.8,
    genres: ['Crime', 'Drama'],
    overview: 'Late-night cases in a city that never fully wakes.',
    runtimeTicks: 31_200_000_000,
    positionTicks: null,
    backdropUrl: 'linear-gradient(160deg, #312e81, #0f172a 60%)',
    thumbUrl: 'linear-gradient(160deg, #312e81, #0f172a 60%)',
  },
  {
    id: 'jf-dune-resume',
    parentId: null,
    title: 'Dune',
    subtitle: '',
    kind: 'movie',
    posterUrl: 'linear-gradient(145deg, #8b5a2b, #1a1410 70%)',
    playable: true,
    progressPercent: 18,
    year: 2021,
    rating: 8.4,
    genres: ['Sci-Fi', 'Adventure'],
    overview: 'A mythic desert world and the fight for its spice.',
    runtimeTicks: 93_600_000_000,
    positionTicks: 16_848_000_000,
    backdropUrl: 'linear-gradient(160deg, #8b5a2b, #1a1410 60%)',
    thumbUrl: 'linear-gradient(160deg, #8b5a2b, #1a1410 60%)',
  },
  {
    id: 'jf-night-transit-resume',
    parentId: null,
    title: 'Night Transit',
    subtitle: '',
    kind: 'movie',
    artworkState: 'missing',
    playable: true,
    progressPercent: 6,
    year: 2026,
    rating: null,
    genres: ['Thriller'],
    overview: null,
    runtimeTicks: 66_000_000_000,
    positionTicks: 3_960_000_000,
    backdropUrl: null,
    thumbUrl: null,
  },
];

function demoStorageOverview(): MediaStackStorageOverviewDto {
  return {
    ok: true,
    generatedAt: new Date().toISOString(),
    volumes: [
      {
        id: 'media-volume',
        label: 'Media volume (/data)',
        kind: 'library',
        usedBytes: Math.round(4.8 * TIB),
        totalBytes: Math.round(7.2 * TIB),
      },
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
    played: true,
    episodeCount: null,
  },
  {
    id: 'jf-afterlight',
    title: 'Afterlight',
    kind: 'movie',
    year: 2026,
    overview: 'A crew races the last light across a dying colony.',
    posterUrl: 'linear-gradient(145deg, #3d5a80, #0d1117 70%)',
    playable: true,
    played: false,
  },
  {
    id: 'jf-orbit',
    title: 'Orbit Station',
    kind: 'movie',
    year: 2024,
    overview: 'Docking bay politics at the edge of settled space.',
    posterUrl: 'linear-gradient(145deg, #4a5568, #111827 70%)',
    playable: true,
    played: false,
  },
  {
    id: 'jf-night-transit',
    title: 'Night Transit',
    kind: 'movie',
    year: 2026,
    overview: 'A premiere without artwork in the demo catalog.',
    artworkState: 'missing',
    playable: true,
    played: false,
  },
  {
    id: 'jf-cowboy-bebop',
    title: 'Cowboy Bebop',
    kind: 'series',
    year: 1998,
    overview: 'Bounty hunters chasing the past across the solar system.',
    posterUrl: 'linear-gradient(145deg, #b45309, #1c1917 70%)',
    playable: true,
    played: false,
    episodeCount: 26,
  },
  {
    id: 'jf-the-expanse',
    title: 'The Expanse',
    kind: 'series',
    year: 2015,
    overview: 'Politics and survival between Earth, Mars, and the Belt.',
    posterUrl: 'linear-gradient(145deg, #1e3a5f, #0b1220 70%)',
    playable: true,
    played: false,
    episodeCount: 10,
  },
  {
    id: 'jf-blue-hour',
    title: 'The Blue Hour',
    kind: 'series',
    year: 2023,
    overview: 'Late-night cases in a city that never fully wakes.',
    posterUrl: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
    playable: true,
    played: false,
    episodeCount: 8,
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
    played: false,
    episodeCount: 1,
  },
];

function demoAutomationSummary(): MediaStackAutomationSummaryDto {
  return {
    generatedAt: new Date().toISOString(),
    services: [
      { id: 'jellyfin', name: 'Jellyfin', status: 'healthy', detail: 'Streaming ready', latencyMs: 18 },
      { id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'Indexers reachable', latencyMs: 20 },
      { id: 'radarr', name: 'Radarr', status: 'healthy', detail: 'Indexers reachable', latencyMs: 22 },
      { id: 'prowlarr', name: 'Prowlarr', status: 'degraded', detail: '5/8 enabled · 1 off · 1 cooldown', latencyMs: 350 },
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
      {
        id: 'prowlarr-disabled',
        summary: '1 indexer(s) disabled',
        serviceId: 'prowlarr',
        severity: 'warning',
        items: [{ title: 'SlowIndex', when: 'disabled', href: null, posterUrl: null }],
        itemCount: 1,
      },
      {
        id: 'prowlarr-cooldown',
        summary: '1 indexer(s) in cooldown',
        serviceId: 'prowlarr',
        severity: 'warning',
        items: [{ title: 'CoolIndex', when: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(), href: null, posterUrl: null }],
        itemCount: 1,
      },
      {
        id: 'sonarr-missing',
        summary: '4 Sonarr episode(s) missing',
        serviceId: 'sonarr',
        severity: 'warning',
        items: [
          { title: 'The Apothecary Diaries S1E24', when: '2026-03-24T14:00:00Z', href: 'http://localhost:8989/series/the-apothecary-diaries' },
          { title: 'The Apothecary Diaries S1E23', when: '2026-03-17T14:00:00Z', href: 'http://localhost:8989/series/the-apothecary-diaries' },
          { title: 'Sparks of Tomorrow S1E4', when: '2026-07-26T14:00:00Z', href: 'http://localhost:8989/series/sparks-of-tomorrow' },
          { title: 'Sparks of Tomorrow S1E2', when: '2026-07-12T14:00:00Z', href: 'http://localhost:8989/series/sparks-of-tomorrow' },
        ],
        itemCount: 4,
      },
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

/** Demo activity is relative to now so the right-rail "xm ago" column stays fresh. */
function demoActivityFeed(now = Date.now()): MediaStackActivityFeedDto {
  const ago = (minutes: number): string => new Date(now - minutes * 60_000).toISOString();
  return {
    ok: true,
    generatedAt: new Date(now).toISOString(),
    sources: { sonarr: 'ok', radarr: 'ok' },
    items: [
      { id: 'sonarr:48211', source: 'sonarr', kind: 'imported', title: 'Cowboy Bebop', subtitle: 'S01E05 · 1080p WEB-DL', timestamp: ago(4), href: 'http://localhost:8989/series/cowboy-bebop' },
      { id: 'radarr:9021', source: 'radarr', kind: 'grabbed', title: 'Dune', subtitle: '2021 · 2160p WEB-DL', timestamp: ago(11), href: 'http://localhost:7878/movie/dune-2021' },
      { id: 'sonarr:48190', source: 'sonarr', kind: 'grabbed', title: 'The Blue Hour', subtitle: 'S02E03 · 1080p HDTV', timestamp: ago(26), href: 'http://localhost:8989/series/the-blue-hour' },
      { id: 'radarr:9014', source: 'radarr', kind: 'imported', title: 'Orbit Station', subtitle: '2024 · 1080p BluRay', timestamp: ago(63), href: 'http://localhost:7878/movie/orbit-station' },
      { id: 'sonarr:48102', source: 'sonarr', kind: 'failed', title: 'Silent Wave', subtitle: 'S01E06 · 1080p WEB-DL', timestamp: ago(140), href: 'http://localhost:8989/series/silent-wave' },
      { id: 'radarr:8990', source: 'radarr', kind: 'deleted', title: 'Dust Road', subtitle: '2025 · 720p HDTV', timestamp: ago(320), href: null },
    ],
  };
}

function copyCronLogs(source: MediaStackCronLogsDto): MediaStackCronLogsDto {
  return {
    ...source,
    logs: (source.logs ?? []).map(
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
export type DownloadsScenario = 'default' | 'empty' | 'error' | 'paused' | 'mixed';
export type WatchNextScenario = 'default' | 'empty';

function demoRecentlyAvailable(now = Date.now()): MediaStackRecentlyAvailableItemDto[] {
  const iso = (offsetMs: number) => new Date(now - offsetMs).toISOString();
  return [
    {
      id: 'demo-ra-ep-30m',
      parentId: 'demo-series-1',
      kind: 'episode',
      title: 'Saga of Tanya the Evil',
      subtitle: 'S02E05 · Lamb',
      year: 2026,
      availableAt: iso(30 * 60_000),
      posterUrl: 'https://example.com/tanya.jpg',
      artworkState: 'ok',
      thumbUrl: 'https://example.com/tanya-thumb.jpg',
      playable: true,
    },
    {
      id: 'demo-ra-ep-4h',
      parentId: 'demo-series-2',
      kind: 'episode',
      title: 'The Expanse',
      subtitle: 'S06E06 · Exodus',
      year: 2022,
      availableAt: iso(4 * 60 * 60_000),
      posterUrl: 'https://example.com/expanse.jpg',
      artworkState: 'ok',
      thumbUrl: null,
      playable: true,
    },
    {
      id: 'demo-ra-movie-30h',
      parentId: null,
      kind: 'movie',
      title: 'Mickey 17',
      subtitle: '',
      year: 2025,
      availableAt: iso(30 * 60 * 60_000),
      posterUrl: undefined,
      artworkState: 'missing',
      thumbUrl: null,
      playable: true,
    },
    {
      id: 'demo-ra-ep-3d',
      parentId: 'demo-series-3',
      kind: 'episode',
      title: 'House of the Dragon',
      subtitle: 'S02E01 · A Son for a Son',
      year: 2024,
      availableAt: iso(3 * 24 * 60 * 60_000),
      posterUrl: 'https://example.com/hotd.jpg',
      artworkState: 'ok',
      thumbUrl: 'https://example.com/hotd-thumb.jpg',
      playable: true,
    },
    {
      id: 'demo-ra-movie-8d',
      parentId: null,
      kind: 'movie',
      title: 'Dune: Part Two',
      subtitle: '',
      year: 2024,
      availableAt: iso(8 * 24 * 60 * 60_000),
      posterUrl: 'https://example.com/dune2.jpg',
      artworkState: 'ok',
      thumbUrl: null,
      playable: true,
    },
  ];
}

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
  private watchNextItems = DEMO_WATCH_NEXT.map((item) => ({ ...item }));
  private automationScenario: AutomationScenario = 'default';
  private downloadsScenario: DownloadsScenario = 'default';
  private watchNextScenario: WatchNextScenario = 'default';
  demoDeletePartial = false;

  /**
   * Artificial Demo-mode latency in ms so skeleton loading states are visible.
   * Default is 0 (deterministic, fast tests/dev). Demos opt in via ?latency=<ms> URL param.
   * Each read resolves after latencyMs * (0.6..1.4).
   */
  latencyMs = 0;

  protected withLatency<T>(value: T): Promise<T> {
    if (this.latencyMs <= 0) {
      return Promise.resolve(value);
    }
    // Jitter is intentional for staggered demo skeleton reveals (not security-sensitive).
    // eslint-disable-next-line sonarjs/pseudo-random -- demo UI timing only
    const delay = this.latencyMs * (0.6 + Math.random() * 0.8);
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve(value);
      }, delay);
    });
  }

  setAutomationScenario(scenario: AutomationScenario): void {
    this.automationScenario = scenario;
  }

  setWatchNextScenario(scenario: WatchNextScenario): void {
    this.watchNextScenario = scenario;
  }

  setDownloadsScenario(scenario: DownloadsScenario): void {
    this.downloadsScenario = scenario;
    switch (scenario) {
      case 'empty':
        this.torrents = [];
        break;
      case 'paused':
        this.torrents = DEMO_TORRENTS.map((torrent) => ({ ...torrent, state: 'paused', dlspeed: 0, upspeed: 0 }));
        break;
      case 'mixed':
        this.torrents = MIXED_TORRENTS.map((torrent) => ({ ...torrent }));
        break;
      default:
        this.torrents = DEMO_TORRENTS.map((torrent) => ({ ...torrent }));
    }
  }

  listTorrents(_signal?: AbortSignal): Promise<DownloadTorrent[]> {
    if (this.downloadsScenario === 'error') {
      return Promise.reject(new Error('qBittorrent unavailable'));
    }
    return this.withLatency(this.torrents.map((torrent) => mapTorrent({ ...torrent })));
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
      state: torrent.progress >= 1 ? 'stalledUP' : 'downloading',
      dlspeed: demo?.dlspeed ?? 0,
      upspeed: demo?.upspeed ?? 0,
    };
  }

  listCalendarEvents(_signal?: AbortSignal): Promise<CalendarEvent[]> {
    const events = demoCalendar()
      .sort((left, right) => (left.airDate ?? '').localeCompare(right.airDate ?? ''))
      .map(mapCalendarEvent);
    return this.withLatency(events);
  }

  getArrLibrary(_signal?: AbortSignal): Promise<ArrLibrary> {
    return this.withLatency(
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
    const movieCount = items.filter((item) => item.kind === 'movie').length;
    const seriesCount = items.filter((item) => item.kind === 'series').length;
    return this.withLatency({ items, availability: 'complete', movieCount, seriesCount });
  }

  setLibraryItemPlayed(id: string, played: boolean): Promise<{ played: boolean }> {
    const item = this.libraryItems.find((row) => row.id === id);
    if (!item) {
      return Promise.reject(new Error('Library item not found'));
    }
    item.played = played;
    return this.withLatency({ played });
  }

  previewLibraryItemDeletion(id: string): Promise<LibraryDeletePreview> {
    const item = this.libraryItems.find((row) => row.id === id);
    if (!item) {
      return Promise.reject(new Error('Library item not found'));
    }
    const mapped = mapLibraryItem({ ...item });
    if (!mapped) {
      return Promise.reject(new Error('Library item not found'));
    }
    const expiresAt = new Date(Date.now() + 120_000).toISOString();
    return this.withLatency({
      previewId: `demo-preview-${id}`,
      title: mapped.title,
      kind: mapped.kind,
      manager: mapped.kind === 'movie' ? 'Radarr' : 'Sonarr',
      episodeCount: mapped.episodeCount,
      torrentCount: 1,
      expiresAt,
    });
  }

  deleteLibraryItem(id: string, previewId: string): Promise<LibraryDeleteResult> {
    if (previewId !== `demo-preview-${id}`) {
      return Promise.reject(new Error('Invalid preview'));
    }
    if (this.demoDeletePartial) {
      return this.withLatency({
        ok: false,
        removed: false,
        partial: true,
        torrentCount: 1,
        error: 'Unable to finish deletion',
        steps: { torrents: 'ok', library: 'failed', jellyfin: 'skipped' },
      });
    }
    const index = this.libraryItems.findIndex((row) => row.id === id);
    if (index < 0) {
      return Promise.reject(new Error('Library item not found'));
    }
    this.libraryItems.splice(index, 1);
    return this.withLatency({
      ok: true,
      removed: true,
      torrentCount: 1,
      jellyfinRefresh: 'ok',
      warning: null,
      steps: { torrents: 'ok', library: 'ok', jellyfin: 'ok' },
    });
  }

  listWatchNext(_signal?: AbortSignal): Promise<WatchNextResult> {
    if (this.watchNextScenario === 'empty') {
      return this.withLatency(mapWatchNextResult([]));
    }
    return this.withLatency(mapWatchNextResult(this.watchNextItems.map((item) => ({ ...item }))));
  }

  listRecentlyAvailable(limit?: number, _signal?: AbortSignal): Promise<RecentlyAvailableResult> {
    const base = limit ?? 10;
    const safe = Number.isFinite(base) ? base : 10;
    const normalized = Math.max(1, Math.min(50, Math.floor(safe)));
    const items = demoRecentlyAvailable().slice(0, normalized).map((item) => ({ ...item }));
    return this.withLatency(mapRecentlyAvailableResult(items));
  }

  getActivity(limit = 20, _signal?: AbortSignal): Promise<ActivityFeed> {
    const clamped = Number.isFinite(limit) ? Math.max(1, Math.min(50, Math.floor(limit))) : 20;
    const feed = demoActivityFeed();
    return this.withLatency(mapActivityFeed({ ...feed, items: feed.items.slice(0, clamped) }));
  }

  getLibraryStats(_signal?: AbortSignal): Promise<LibraryStats> {
    return this.withLatency(mapLibraryStats({ ...DEMO_LIBRARY_STATS }));
  }

  getStorageOverview(_signal?: AbortSignal): Promise<StorageOverview> {
    return this.withLatency(mapStorageOverview(demoStorageOverview()));
  }

  getAutomationSummary(_signal?: AbortSignal): Promise<AutomationSummary> {
    let summary;
    if (this.automationScenario === 'partial') {
      summary = PARTIAL_AUTOMATION_SUMMARY;
    } else if (this.automationScenario === 'empty') {
      summary = { generatedAt: new Date().toISOString(), services: [], preview: [], problems: [] };
    } else {
      summary = demoAutomationSummary();
    }
    return this.withLatency(mapAutomationSummary(structuredClone(summary)));
  }

  listCronLogs(_signal?: AbortSignal): Promise<CronLogs> {
    return this.withLatency(mapCronLogs(copyCronLogs(demoCronLogs())));
  }

  listHermesRecommendations(_signal?: AbortSignal): Promise<HermesDiscover> {
    const pending_request_sync = this.hermesItems
      .filter((item) => item.id === MOCK_SYNC_FAILED_HERMES_ID && item.jellyseerr_request_id && item.request_state == null)
      .map((item) => ({ id: item.id, jellyseerr_request_id: item.jellyseerr_request_id as number }));
    return this.withLatency(
      mapHermesDiscover({
        ok: true,
        items: this.hermesItems.map((item) => ({ ...item })),
        pending_request_sync,
        generation_request: this.hermesMorePending && this.hermesMoreRequestedAt
          ? { requested_at: this.hermesMoreRequestedAt, status: 'pending' }
          : null,
        watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      }),
    );
  }

  submitHermesFeedback(
    id: string,
    feedback: DiscoverFeedback,
    options?: SubmitHermesFeedbackOptions,
  ): Promise<DiscoverAction> {
    const item = this.hermesItems.find((candidate) => candidate.id === id);
    if (!item) {
      return Promise.resolve(mapDiscoverAction({ ok: false, error: 'Recommendation not found' }));
    }
    if (feedback === 'watched' && item.type === 'tv' && !options?.confirmAllAired) {
      return Promise.resolve(
        mapDiscoverAction({
          ok: false,
          code: 'confirmation_required',
          error: 'Confirmation required',
        }),
      );
    }
    item.feedback = feedback;
    item.feedback_at = new Date().toISOString();
    item.active = false;
    if (options?.notes !== undefined) {
      item.notes = options.notes;
    }
    if (feedback === 'watched') {
      item.trakt_history_sync = { status: 'synced' };
    }
    return Promise.resolve(
      mapDiscoverAction({
        ok: true,
        message: 'Feedback saved',
        ...(feedback === 'watched'
          ? { trakt_history_sync: item.trakt_history_sync ?? { status: 'synced' } }
          : {}),
      }),
    );
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

  listJellyseerrDiscover(kind: JellyseerrDiscoverKind, _signal?: AbortSignal): Promise<ExternalDiscover> {
    return this.withLatency(
      mapExternalDiscover({
        ok: true,
        items: DEMO_JELLYSEERR[kind].map((item) => ({ ...item })),
      }),
    );
  }

  listTraktDiscover(type: TraktDiscoverType, _signal?: AbortSignal): Promise<ExternalDiscover> {
    return this.withLatency(
      mapExternalDiscover({
        ok: true,
        items: DEMO_TRAKT[type].map((item) => ({ ...item })),
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
