import { MediaStackApi } from './media-stack-api';
import { MockMediaStackApi } from './mock-media-stack-api';

describe('MockMediaStackApi', () => {
  it('provides deterministic torrents and supports pause/resume all', async () => {
    const api: MediaStackApi = new MockMediaStackApi();
    const initial = await api.listTorrents();
    expect(initial.map((torrent) => torrent.hash)).toEqual(['demo-afterlight', 'demo-blue-hour', 'demo-orbit']);
    expect(initial.filter((torrent) => torrent.state === 'downloading')).toHaveLength(2);

    await api.pauseAll();
    expect((await api.listTorrents()).every((torrent) => torrent.state === 'paused')).toBe(true);
    await api.resumeAll();
    expect((await api.listTorrents()).filter((torrent) => torrent.state === 'downloading')).toHaveLength(2);
  });
});
