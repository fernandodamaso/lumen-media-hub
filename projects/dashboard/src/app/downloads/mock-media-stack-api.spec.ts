import { MediaStackApi, normalizeTorrent, summarizeDownloads } from './media-stack-api';
import { MockMediaStackApi } from './mock-media-stack-api';

describe('MockMediaStackApi', () => {
  it('provides deterministic torrents and supports pause/resume all', async () => {
    const api: MediaStackApi = new MockMediaStackApi();
    const initial = await api.listTorrents();
    expect(initial.map((torrent) => torrent.hash)).toEqual(['demo-afterlight', 'demo-blue-hour', 'demo-orbit']);
    expect(initial.filter((torrent) => torrent.state === 'downloading')).toHaveLength(2);

    await api.pauseAll();
    const paused = await api.listTorrents();
    expect(paused.every((torrent) => torrent.state === 'paused' && torrent.dlspeed === 0 && torrent.upspeed === 0)).toBe(true);
    expect(summarizeDownloads(paused.map(normalizeTorrent))).toMatchObject({ downloadRate: 0, uploadRate: 0 });
    await api.resumeAll();
    const resumed = await api.listTorrents();
    expect(resumed.map(({ hash, dlspeed, upspeed }) => ({ hash, dlspeed, upspeed }))).toEqual(initial.map(({ hash, dlspeed, upspeed }) => ({ hash, dlspeed, upspeed })));
  });
});
