import { DownloadTorrent } from './downloads.models';

export const COMPLETED_VISIBILITY_MS = 24 * 60 * 60 * 1000;
export const HIDDEN_COMPLETED_STORAGE_KEY = 'lumen.downloads.hidden-completed.v1';

export interface DownloadsVisibilityStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

function browserStorage(): DownloadsVisibilityStorage | null {
  try {
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

export function isTorrentVisible(
  torrent: DownloadTorrent,
  nowMs: number,
  dismissedIds: ReadonlySet<string>,
): boolean {
  if (!torrent.completed) return true;
  if (dismissedIds.has(torrent.id)) return false;
  if (!torrent.completedAt) return true;
  const completedAtMs = Date.parse(torrent.completedAt);
  if (!Number.isFinite(completedAtMs) || completedAtMs > nowMs) return true;
  return nowMs - completedAtMs < COMPLETED_VISIBILITY_MS;
}

export class DownloadsVisibilityStore {
  constructor(private readonly storage: DownloadsVisibilityStorage | null = browserStorage()) {}

  load(): Set<string> {
    if (!this.storage) return new Set();
    try {
      const raw = this.storage.getItem(HIDDEN_COMPLETED_STORAGE_KEY);
      const parsed: unknown = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(parsed)) return new Set();
      return new Set(
        parsed.filter((id): id is string => typeof id === 'string' && id.trim().length > 0).map((id) => id.trim()),
      );
    } catch {
      return new Set();
    }
  }

  save(ids: ReadonlySet<string>): void {
    if (!this.storage) return;
    try {
      const normalized = [...ids].filter((id) => id.trim()).map((id) => id.trim()).sort((a, b) => a.localeCompare(b));
      this.storage.setItem(HIDDEN_COMPLETED_STORAGE_KEY, JSON.stringify([...new Set(normalized)]));
    } catch {
      // Private browsing/quota errors must not break dashboard operation.
    }
  }
}
