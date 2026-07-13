import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { MEDIA_STACK_API, MediaStackApi, MediaStackTorrentDto } from './media-stack-api';
import { DownloadsFacade } from './downloads.facade';

const torrent: MediaStackTorrentDto = { hash: 'a', name: 'A', state: 'downloading', progress: .5, size: 100, downloaded: 50, dlspeed: 10, upspeed: 2, eta: 30 };

describe('DownloadsFacade', () => {
  let api: MockApi;
  let facade: DownloadsFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({ providers: [DownloadsFacade, { provide: MEDIA_STACK_API, useValue: api }] });
    facade = TestBed.inject(DownloadsFacade);
  });

  it('polls and exposes populated, empty, and error states', async () => {
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    api.items = [];
    await facade.refresh();
    expect(facade.status()).toBe('empty');
    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');
  });

  it('prevents conflicting actions and refreshes after success', async () => {
    let release!: () => void;
    api.action = new Promise<void>((resolve) => { release = resolve; });
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

  it('keeps a failed action recoverable', async () => {
    api.actionFailure = true;
    await facade.runAction('pause');
    expect(facade.pendingAction()).toBeNull();
    expect(facade.status()).toBe('error');
    expect(facade.notice()).toBe('');
    api.actionFailure = false;
    await facade.runAction('resume');
    expect(facade.pendingAction()).toBeNull();
    expect(facade.notice()).toBe('All downloads resumed.');
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
});

class MockApi implements MediaStackApi {
  items: MediaStackTorrentDto[] = [{ ...torrent }];
  actions: string[] = [];
  listCalls = 0;
  failure = false;
  actionFailure = false;
  action: Promise<void> = Promise.resolve();
  listTorrents(): Promise<MediaStackTorrentDto[]> { this.listCalls++; return this.failure ? Promise.reject(new Error('offline')) : Promise.resolve(this.items); }
  pauseAll(): Promise<void> { this.actions.push('pause'); return this.actionFailure ? Promise.reject(new Error('failed')) : this.action; }
  resumeAll(): Promise<void> { this.actions.push('resume'); return this.actionFailure ? Promise.reject(new Error('failed')) : this.action; }
  listCalendarEvents() { return Promise.resolve([]); }
  getArrLibrary() { return Promise.resolve({ ok: true, series: {}, movies: {} }); }
  listHermesRecommendations() { return Promise.resolve({ ok: true, items: [] }); }
  submitHermesFeedback() { return Promise.resolve({ ok: true }); }
  requestHermesMore() { return Promise.resolve({ ok: true }); }
  listJellyseerrDiscover() { return Promise.resolve({ ok: true, items: [] }); }
  listTraktDiscover() { return Promise.resolve({ ok: true, items: [] }); }
  requestMedia() { return Promise.resolve({ ok: true }); }
}
