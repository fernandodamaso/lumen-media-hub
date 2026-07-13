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

  it('provides ordered mixed calendar events and arr library mappings', async () => {
    const api: MediaStackApi = new MockMediaStackApi();
    const events = await api.listCalendarEvents();
    expect(events.map((event) => event.title)).toEqual([
      'Cowboy Bebop',
      'Dune',
      'The Expanse',
      'Night Transit',
    ]);
    expect(events.some((event) => event.kind === 'episode')).toBe(true);
    expect(events.some((event) => event.kind === 'movie')).toBe(true);

    const library = await api.getArrLibrary();
    expect(library.series['cowboy bebop']).toBe('cowboy-bebop');
    expect(library.movies['dune']).toBe('dune-2021');
    expect(library.movies['night transit']).toBeUndefined();
  });

  it('lists library items with kind filter and defensive copies', async () => {
    const api: MediaStackApi = new MockMediaStackApi();
    const all = await api.listLibraryItems();
    expect(all.filter((item) => item.kind === 'movie').length).toBeGreaterThanOrEqual(3);
    expect(all.filter((item) => item.kind === 'series').length).toBeGreaterThanOrEqual(3);
    expect(all.some((item) => item.artworkState === 'missing')).toBe(true);
    expect(all.some((item) => item.artworkState === 'failed')).toBe(true);

    const movies = await api.listLibraryItems({ kind: 'movie' });
    expect(movies.every((item) => item.kind === 'movie')).toBe(true);

    const first = movies[0];
    first.title = 'Mutated';
    const again = await api.listLibraryItems({ kind: 'movie' });
    expect(again[0].title).not.toBe('Mutated');
  });
});
