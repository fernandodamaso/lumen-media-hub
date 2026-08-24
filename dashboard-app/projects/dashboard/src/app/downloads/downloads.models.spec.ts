import { DownloadTorrent, summarizeDownloads } from './downloads.models';

describe('downloads.models', () => {
  it('groups totals and active downloads from domain torrents', () => {
    const downloading: DownloadTorrent = {
      id: 'a',
      name: 'A',
      state: 'downloading',
      progress: 50,
      size: 100,
      downloaded: 50,
      downloadRate: 10,
      uploadRate: 2,
      eta: 30,
      category: 'Uncategorized',
      completed: false,
      completedAt: null,
    };
    const seeding: DownloadTorrent = {
      id: 'b',
      name: 'B',
      state: 'seeding',
      progress: 100,
      size: 200,
      downloaded: 200,
      downloadRate: 0,
      uploadRate: 3,
      eta: 0,
      category: 'Uncategorized',
      completed: true,
      completedAt: null,
    };
    expect(summarizeDownloads([downloading, seeding])).toEqual({
      active: 1,
      total: 2,
      downloaded: 250,
      size: 300,
      downloadRate: 10,
      uploadRate: 5,
    });
  });
});
