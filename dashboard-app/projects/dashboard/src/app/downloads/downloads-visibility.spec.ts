import { DownloadTorrent } from './downloads.models';
import {
  COMPLETED_VISIBILITY_MS,
  DownloadsVisibilityStore,
  HIDDEN_COMPLETED_STORAGE_KEY,
  isTorrentVisible,
} from './downloads-visibility';

class MemoryStorage {
  private values = new Map<string, string>();
  throwOnWrite = false;
  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  setItem(key: string, value: string): void {
    if (this.throwOnWrite) throw new Error('quota');
    this.values.set(key, value);
  }
}

const base: DownloadTorrent = {
  id: 'hash-a', name: 'A', state: 'seeding', progress: 100, size: 100, downloaded: 100,
  downloadRate: 0, uploadRate: 2, eta: 0, category: 'sonarr', completed: true,
  completedAt: '2026-08-23T00:00:00.000Z',
};

describe('downloads visibility', () => {
  const now = Date.parse('2026-08-24T00:00:00.000Z');

  it('keeps incomplete torrents visible even when dismissed', () => {
    expect(isTorrentVisible({ ...base, completed: false, progress: 50 }, now, new Set(['hash-a']))).toBe(true);
  });

  it('hides completed torrents at or after 24 hours', () => {
    expect(isTorrentVisible({ ...base, completedAt: new Date(now - COMPLETED_VISIBILITY_MS + 1).toISOString() }, now, new Set())).toBe(true);
    expect(isTorrentVisible({ ...base, completedAt: new Date(now - COMPLETED_VISIBILITY_MS).toISOString() }, now, new Set())).toBe(false);
  });

  it('keeps unknown or future completion timestamps visible', () => {
    expect(isTorrentVisible({ ...base, completedAt: null }, now, new Set())).toBe(true);
    expect(isTorrentVisible({ ...base, completedAt: 'not-a-date' }, now, new Set())).toBe(true);
    expect(isTorrentVisible({ ...base, completedAt: new Date(now + 1).toISOString() }, now, new Set())).toBe(true);
  });

  it('hides manually dismissed completed torrents immediately', () => {
    expect(isTorrentVisible(base, now, new Set(['hash-a']))).toBe(false);
  });

  it('loads malformed storage as empty and saves normalized hashes only', () => {
    const storage = new MemoryStorage();
    const store = new DownloadsVisibilityStore(storage);
    storage.setItem(HIDDEN_COMPLETED_STORAGE_KEY, '{bad');
    expect(store.load()).toEqual(new Set());
    store.save(new Set([' hash-b ', 'hash-a', 'hash-a']));
    expect(storage.getItem(HIDDEN_COMPLETED_STORAGE_KEY)).toBe('["hash-a","hash-b"]');
  });

  it('survives storage write failures', () => {
    const storage = new MemoryStorage();
    storage.throwOnWrite = true;
    expect(() => { new DownloadsVisibilityStore(storage).save(new Set(['hash-a'])); }).not.toThrow();
  });
});
