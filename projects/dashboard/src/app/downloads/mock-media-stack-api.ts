import { Injectable } from '@angular/core';
import {
  MediaStackApi,
  MediaStackArrLibraryDto,
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

@Injectable()
export class MockMediaStackApi implements MediaStackApi {
  private torrents = DEMO_TORRENTS.map((torrent) => ({ ...torrent }));
  private calendar = DEMO_CALENDAR.map((event) => ({ ...event }));
  private library: MediaStackArrLibraryDto = {
    ok: DEMO_LIBRARY.ok,
    series: { ...DEMO_LIBRARY.series },
    movies: { ...DEMO_LIBRARY.movies },
  };

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
}
