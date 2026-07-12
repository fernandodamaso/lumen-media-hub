import { Injectable } from '@angular/core';
import { MediaStackApi, MediaStackTorrentDto } from './media-stack-api';

const DEMO_TORRENTS: MediaStackTorrentDto[] = [
  { hash: 'demo-afterlight', name: 'Afterlight', state: 'downloading', progress: 0.68, size: 7_400_000_000, downloaded: 5_032_000_000, dlspeed: 4_200_000, upspeed: 320_000, eta: 540, category: 'Movies' },
  { hash: 'demo-blue-hour', name: 'The Blue Hour', state: 'downloading', progress: 0.31, size: 2_100_000_000, downloaded: 651_000_000, dlspeed: 1_800_000, upspeed: 80_000, eta: 800, category: 'TV' },
  { hash: 'demo-orbit', name: 'Orbit Station', state: 'stoppedUP', progress: 1, size: 5_800_000_000, downloaded: 5_800_000_000, dlspeed: 0, upspeed: 120_000, eta: 0, category: 'Movies' },
];

@Injectable()
export class MockMediaStackApi implements MediaStackApi {
  private torrents = DEMO_TORRENTS.map((torrent) => ({ ...torrent }));

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
}
