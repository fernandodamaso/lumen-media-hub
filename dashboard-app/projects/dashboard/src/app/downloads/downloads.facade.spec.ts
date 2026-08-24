import { mediaStackLibraryMutationStub } from '../../testing/media-stack-library-stub';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { DownloadTorrent } from './downloads.models';
import { DownloadsFacade, SCHEDULED_REFRESH_TIMEOUT_MS } from './downloads.facade';
import { HIDDEN_COMPLETED_STORAGE_KEY } from './downloads-visibility';

const torrent: DownloadTorrent = {
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

describe('DownloadsFacade', () => {
  let api: MockApi;
  let facade: DownloadsFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({ providers: [DownloadsFacade, { provide: MEDIA_STACK_API, useValue: api }] });
    facade = TestBed.inject(DownloadsFacade);
  });

  it('polls and exposes populated, empty, and error states', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.refreshing()).toBe(false);
    api.items = [];
    await facade.refresh();
    expect(facade.status()).toBe('empty');
    api.failure = true;
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');
  });

  it('retains last-good rows when a background refresh fails', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.torrents()).toHaveLength(1);

    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.torrents()).toHaveLength(1);
    expect(facade.error()).toContain('Showing last loaded queue');
  });

  it('ignores stale responses when a newer refresh wins the race', async () => {
    const { promise: initialPromise, resolve: resolveInitial } =
      Promise.withResolvers<DownloadTorrent[]>();
    api.nextResponse = initialPromise;

    const first = facade.refresh({ initial: true });
    expect(facade.refreshing()).toBe(true);

    api.nextResponse = undefined;
    api.items = [{ ...torrent, id: 'newer', name: 'Newer' }];
    await facade.refresh();
    expect(facade.torrents()[0]?.id).toBe('newer');

    resolveInitial([{ ...torrent, id: 'stale', name: 'Stale' }]);
    await first;

    expect(facade.torrents()[0]?.id).toBe('newer');
    expect(facade.refreshing()).toBe(false);
  });

  it('does not overlap scheduled polls while one is in flight', async () => {
    vi.useFakeTimers();
    const { promise: deferred, resolve } = Promise.withResolvers<DownloadTorrent[]>();
    api.nextResponse = deferred;

    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.listCalls).toBe(1);

    await vi.advanceTimersByTimeAsync(300);
    expect(api.listCalls).toBe(1);

    api.nextResponse = undefined;
    resolve([{ ...torrent }]);
    await Promise.resolve();
    await Promise.resolve();

    await vi.advanceTimersByTimeAsync(100);
    expect(api.listCalls).toBe(2);

    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(200);
    expect(api.listCalls).toBe(2);
    vi.useRealTimers();
  });

  it('recovers scheduled polling after a hung refresh times out', async () => {
    vi.useFakeTimers();
    const { promise: deferred } = Promise.withResolvers<DownloadTorrent[]>();
    api.nextResponse = deferred;

    // Keep the poll interval longer than the hang timeout so interval ticks do not
    // restart refreshes while we assert timeout recovery.
    facade.startPolling(SCHEDULED_REFRESH_TIMEOUT_MS + 1_000);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.listCalls).toBe(1);
    expect(facade.refreshing()).toBe(true);

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(facade.refreshing()).toBe(false);
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');

    api.nextResponse = undefined;
    await vi.advanceTimersByTimeAsync(1_000);
    expect(api.listCalls).toBe(2);
    expect(facade.status()).toBe('ready');
    expect(facade.refreshing()).toBe(false);

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('ignores a superseded hung poll timeout after a newer refresh wins', async () => {
    vi.useFakeTimers();
    const { promise: deferred } = Promise.withResolvers<DownloadTorrent[]>();
    api.nextResponse = deferred;

    facade.startPolling(SCHEDULED_REFRESH_TIMEOUT_MS + 1_000);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.listCalls).toBe(1);
    expect(facade.refreshing()).toBe(true);

    api.nextResponse = undefined;
    api.items = [{ ...torrent, id: 'from-manual', name: 'From manual' }];
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.torrents()[0]?.id).toBe('from-manual');
    expect(facade.error()).toBe('');
    expect(facade.refreshing()).toBe(false);

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(facade.status()).toBe('ready');
    expect(facade.torrents()[0]?.id).toBe('from-manual');
    expect(facade.error()).toBe('');
    expect(facade.refreshing()).toBe(false);

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('aborts the active listTorrents signal when a scheduled refresh times out', async () => {
    vi.useFakeTimers();
    const { promise: deferred } = Promise.withResolvers<DownloadTorrent[]>();
    api.nextResponse = deferred;

    facade.startPolling(SCHEDULED_REFRESH_TIMEOUT_MS + 1_000);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.listCalls).toBe(1);
    expect(api.lastSignal?.aborted).toBe(false);

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(api.lastSignal?.aborted).toBe(true);
    expect(api.listCalls).toBe(1);

    api.nextResponse = undefined;
    await vi.advanceTimersByTimeAsync(1_000);
    expect(api.listCalls).toBe(2);

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('does not start a second scheduled request until the timed-out one is aborted', async () => {
    vi.useFakeTimers();
    const { promise: deferred } = Promise.withResolvers<DownloadTorrent[]>();
    api.nextResponse = deferred;

    facade.startPolling(SCHEDULED_REFRESH_TIMEOUT_MS + 1_000);
    await vi.advanceTimersByTimeAsync(0);
    const firstSignal = api.lastSignal;
    expect(api.listCalls).toBe(1);

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS - 1);
    expect(api.listCalls).toBe(1);
    expect(firstSignal?.aborted).toBe(false);

    await vi.advanceTimersByTimeAsync(1);
    expect(firstSignal?.aborted).toBe(true);
    expect(api.listCalls).toBe(1);

    api.nextResponse = undefined;
    await vi.advanceTimersByTimeAsync(1_000);
    expect(api.listCalls).toBe(2);
    expect(api.lastSignal).not.toBe(firstSignal);
    expect(api.lastSignal?.aborted).toBe(false);

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('aborts an active refresh on destroy and ignores a late resolution', async () => {
    vi.useFakeTimers();
    const { promise: deferred, resolve } = Promise.withResolvers<DownloadTorrent[]>();
    api.nextResponse = deferred;

    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.listCalls).toBe(1);
    expect(facade.status()).toBe('loading');
    const signal = api.lastSignal;

    TestBed.resetTestingModule();
    expect(signal?.aborted).toBe(true);

    resolve([{ ...torrent, id: 'late', name: 'Late' }]);
    await Promise.resolve();
    await Promise.resolve();

    expect(facade.status()).toBe('loading');
    expect(facade.torrents()).toEqual([]);
    await vi.advanceTimersByTimeAsync(500);
    expect(api.listCalls).toBe(1);
    vi.useRealTimers();
  });

  it('keeps mutation success notice when a later background refresh fails', async () => {
    await facade.refresh({ initial: true });
    await facade.runAction('pause');
    expect(facade.notice()).toBe('All downloads paused.');

    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.error()).toContain('Showing last loaded queue');
    expect(facade.notice()).toBe('All downloads paused.');
  });

  it('keeps mutation error notice when a later background refresh fails', async () => {
    await facade.refresh({ initial: true });
    api.actionFailure = true;
    await facade.runAction('pause');
    expect(facade.notice()).toContain('Could not pause downloads');

    api.actionFailure = false;
    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.error()).toContain('Showing last loaded queue');
    expect(facade.notice()).toContain('Could not pause downloads');
  });

  it('prevents conflicting actions and refreshes after success', async () => {
    const { promise: actionPromise, resolve } = Promise.withResolvers<undefined>();
    const release = () => {
      resolve(undefined);
    };
    api.action = actionPromise;
    const first = facade.runAction('pause');
    expect(facade.pendingAction()).toBe('pause');
    await facade.runAction('resume');
    expect(api.actions).toEqual(['pause']);
    release();
    await first;
    expect(facade.pendingAction()).toBeNull();
    expect(api.listCalls).toBe(1);
    expect(facade.notice()).toBe('All downloads paused.');
  });

  it('keeps mutation failures from wiping monitored rows', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');

    api.actionFailure = true;
    await facade.runAction('pause');
    expect(facade.pendingAction()).toBeNull();
    expect(facade.status()).toBe('ready');
    expect(facade.torrents()).toHaveLength(1);
    expect(facade.notice()).toContain('Could not pause downloads');

    api.actionFailure = false;
    await facade.runAction('resume');
    expect(facade.pendingAction()).toBeNull();
    expect(facade.notice()).toBe('All downloads resumed.');
  });

  it('guards repeated per-torrent activation', async () => {
    const { promise: actionPromise, resolve } = Promise.withResolvers<undefined>();
    api.torrentAction = actionPromise;
    const first = facade.runTorrentAction('a', 'pause');
    expect(facade.pendingTorrentId()).toBe('a');
    await facade.runTorrentAction('a', 'resume');
    expect(api.torrentActions).toEqual(['pause:a']);
    resolve(undefined);
    await first;
    expect(facade.pendingTorrentId()).toBeNull();
  });

  it('does not let a late mutation refresh overwrite a newer poll', async () => {
    await facade.refresh({ initial: true });

    const { promise: mutationList, resolve: resolveMutationList } =
      Promise.withResolvers<DownloadTorrent[]>();
    api.nextResponse = mutationList;
    const mutation = facade.runTorrentAction('a', 'pause');

    api.nextResponse = undefined;
    api.items = [{ ...torrent, id: 'from-poll', name: 'From poll' }];
    await facade.refresh();
    expect(facade.torrents()[0]?.id).toBe('from-poll');

    resolveMutationList([{ ...torrent, id: 'from-mutation', name: 'From mutation' }]);
    await mutation;

    expect(facade.torrents()[0]?.id).toBe('from-poll');
    expect(facade.pendingTorrentId()).toBeNull();
  });

  it('refreshes on one interval and stops polling when destroyed', async () => {
    vi.useFakeTimers();
    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.listCalls).toBe(1);
    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(200);
    expect(api.listCalls).toBe(3);
    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(200);
    expect(api.listCalls).toBe(3);
    vi.useRealTimers();
  });
  it('filters completed rows after 24 hours while retaining raw summary totals', async () => {
    localStorage.removeItem(HIDDEN_COMPLETED_STORAGE_KEY);
    const now = Date.now();
    api.items = [
      { ...torrent, id: 'old', name: 'Old', completed: true, completedAt: new Date(now - 25 * 60 * 60 * 1000).toISOString(), progress: 100, downloaded: 100 },
      { ...torrent, id: 'fresh', name: 'Fresh', completed: true, completedAt: new Date(now - 2 * 60 * 60 * 1000).toISOString(), progress: 100, downloaded: 100 },
      { ...torrent, id: 'active', name: 'Active', completed: false, completedAt: null },
    ];
    await facade.refresh({ initial: true });
    expect(facade.torrents()).toHaveLength(3);
    expect(facade.visibleTorrents().map((item) => item.id)).toEqual(['fresh', 'active']);
    expect(facade.summary().total).toBe(3);
  });

  it('clears completed rows from the dashboard without calling the API', async () => {
    localStorage.removeItem(HIDDEN_COMPLETED_STORAGE_KEY);
    api.items = [{ ...torrent, completed: true, completedAt: new Date().toISOString(), progress: 100, downloaded: 100 }];
    await facade.refresh({ initial: true });
    const callsBefore = api.listCalls;
    facade.clearCompletedFromView();
    expect(facade.visibleTorrents()).toEqual([]);
    expect(api.listCalls).toBe(callsBefore);
    expect(facade.notice()).toContain('Torrents and files were not removed');
    expect(JSON.parse(localStorage.getItem(HIDDEN_COMPLETED_STORAGE_KEY) ?? '[]')).toEqual(['a']);
  });
});

class MockApi implements MediaStackApi {
  setLibraryItemPlayed = mediaStackLibraryMutationStub.setLibraryItemPlayed;
  previewLibraryItemDeletion = mediaStackLibraryMutationStub.previewLibraryItemDeletion;
  deleteLibraryItem = mediaStackLibraryMutationStub.deleteLibraryItem;
  items: DownloadTorrent[] = [{ ...torrent }];
  actions: string[] = [];
  torrentActions: string[] = [];
  listCalls = 0;
  failure = false;
  actionFailure = false;
  action: Promise<void> = Promise.resolve();
  torrentAction: Promise<void> = Promise.resolve();
  nextResponse?: Promise<DownloadTorrent[]>;
  lastSignal?: AbortSignal;

  listTorrents(signal?: AbortSignal): Promise<DownloadTorrent[]> {
    this.listCalls++;
    this.lastSignal = signal;
    if (signal?.aborted) {
      return Promise.reject(new DOMException('The operation was aborted.', 'AbortError'));
    }
    if (this.nextResponse) {
      const pending = this.nextResponse;
      return new Promise<DownloadTorrent[]>((resolve, reject) => {
        let settled = false;
        const onAbort = () => {
          if (settled) return;
          settled = true;
          reject(new DOMException('The operation was aborted.', 'AbortError'));
        };
        signal?.addEventListener('abort', onAbort, { once: true });
        void pending.then(
          (value) => {
            if (settled) return;
            settled = true;
            signal?.removeEventListener('abort', onAbort);
            resolve(value);
          },
          (error: unknown) => {
            if (settled) return;
            settled = true;
            signal?.removeEventListener('abort', onAbort);
            reject(error instanceof Error ? error : new Error(String(error)));
          },
        );
      });
    }
    return this.failure ? Promise.reject(new Error('offline')) : Promise.resolve(this.items);
  }
  pauseAll(): Promise<void> {
    this.actions.push('pause');
    return this.actionFailure ? Promise.reject(new Error('failed')) : this.action;
  }
  resumeAll(): Promise<void> {
    this.actions.push('resume');
    return this.actionFailure ? Promise.reject(new Error('failed')) : this.action;
  }
  pauseTorrent(id: string): Promise<void> {
    this.torrentActions.push(`pause:${id}`);
    return this.actionFailure ? Promise.reject(new Error('failed')) : this.torrentAction;
  }
  resumeTorrent(id: string): Promise<void> {
    this.torrentActions.push(`resume:${id}`);
    return this.actionFailure ? Promise.reject(new Error('failed')) : this.torrentAction;
  }
  getLibraryStats() {
    return Promise.resolve({ movies: 0, series: 0, availability: 'complete' as const });
  }
  getStorageOverview() {
    return Promise.resolve({ generatedAt: '', volumes: [] });
  }
  listCalendarEvents() {
    return Promise.resolve([]);
  }
  getArrLibrary() {
    return Promise.resolve({ ok: true, series: {}, movies: {} });
  }
  listLibraryItems() {
    return Promise.resolve({ items: [], availability: 'complete' as const });
  }
  listWatchNext() {
    return Promise.resolve({ items: [] });
  }
  listRecentlyAvailable() {
    return Promise.resolve({ items: [] });
  }
  getActivity() {
    return Promise.resolve({
      ok: true,
      generatedAt: '',
      sources: { sonarr: 'ok' as const, radarr: 'ok' as const },
      items: [],
    });
  }
  runQueueHygiene(_mode: 'observe' | 'auto') {
    return Promise.reject(new Error('not implemented'));
  }

  getAutomationSummary() {
    return Promise.resolve({
      generatedAt: '',
      services: [],
      preview: [],
      problems: [],
      queueHygiene: null,
      availability: { services: 'empty' as const, preview: 'empty' as const, problems: 'empty' as const },
    });
  }
  listHermesRecommendations() {
    return Promise.resolve({ ok: true, items: [] });
  }
  submitHermesFeedback() {
    return Promise.resolve({ ok: true });
  }
  requestHermesMore() {
    return Promise.resolve({ ok: true });
  }
  listJellyseerrDiscover() {
    return Promise.resolve({ ok: true, items: [] });
  }
  listTraktDiscover() {
    return Promise.resolve({ ok: true, items: [] });
  }
  requestMedia() {
    return Promise.resolve({ ok: true });
  }
  listCronLogs() {
    return Promise.resolve({ ok: true, currentRuns: [], historyRuns: [] });
  }
}
