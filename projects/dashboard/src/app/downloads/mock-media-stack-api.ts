import { Injectable } from '@angular/core';
import {
  MediaStackApi,
  MediaStackArrLibraryDto,
  MediaStackAutomationSummaryDto,
  MediaStackCalendarEventDto,
  MediaStackTorrentDto,
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

export type AutomationScenario = 'default' | 'partial' | 'empty';

@Injectable()
export class MockMediaStackApi implements MediaStackApi {
  private torrents = DEMO_TORRENTS.map((torrent) => ({ ...torrent }));
  private calendar = DEMO_CALENDAR.map((event) => ({ ...event }));
  private library: MediaStackArrLibraryDto = {
    ok: DEMO_LIBRARY.ok,
    series: { ...DEMO_LIBRARY.series },
    movies: { ...DEMO_LIBRARY.movies },
  };
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

  getAutomationSummary(): Promise<MediaStackAutomationSummaryDto> {
    const summary =
      this.automationScenario === 'partial'
        ? PARTIAL_AUTOMATION_SUMMARY
        : this.automationScenario === 'empty'
          ? { generatedAt: '2026-07-12T18:00:00Z', services: [], preview: [], problems: [] }
          : DEMO_AUTOMATION_SUMMARY;
    return Promise.resolve(structuredClone(summary));
  }
}
