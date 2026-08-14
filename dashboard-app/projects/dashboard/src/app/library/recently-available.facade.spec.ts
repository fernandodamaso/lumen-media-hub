import { mediaStackLibraryMutationStub } from '../../testing/media-stack-library-stub';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { RecentlyAvailableItem } from './recently-available.models';
import { RecentlyAvailableFacade } from './recently-available.facade';

const item = (id: string, availableAt: string): RecentlyAvailableItem => ({
  id,
  parentId: id.startsWith('mv') ? null : 'series-1',
  title: id,
  subtitle: id.startsWith('mv') ? '' : 'S01E01 · Pilot',
  kind: id.startsWith('mv') ? 'movie' : 'episode',
  availableAt,
  art: 'linear-gradient(145deg, #1e3a5f, #0b1220 70%)',
  artworkState: 'ok',
  thumbUrl: null,
  href: null,
  playable: true,
  year: 2026,
});

describe('RecentlyAvailableFacade', () => {
  let api: MockApi;
  let facade: RecentlyAvailableFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [RecentlyAvailableFacade, { provide: MEDIA_STACK_API, useValue: api }],
    });
    facade = TestBed.inject(RecentlyAvailableFacade);
  });

  it('loads items and handles empty and initial error states', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.items()).toHaveLength(1);
    expect(api.lastLimit).toBe(10);

    api.result = { items: [] };
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('empty');

    api.failure = true;
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');
    expect(facade.items()).toEqual([]);
  });

  it('preserves ready items on background failure and recovers on retry', async () => {
    await facade.refresh({ initial: true });
    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.items()).toHaveLength(1);
    expect(facade.error()).toContain('Showing last loaded items');

    api.failure = false;
    await facade.refresh({ initial: true });
    expect(facade.error()).toBe('');
  });

  it('ignores stale responses', async () => {
    const { promise: initialPromise, resolve: resolveInitial } =
      Promise.withResolvers<{ items: RecentlyAvailableItem[] }>();
    api.nextResponse = initialPromise;

    const first = facade.refresh({ initial: true });
    api.nextResponse = undefined;
    api.result = { items: [item('newer', '2026-08-11T12:00:00Z')] };
    await facade.refresh();
    expect(facade.items()[0]?.id).toBe('newer');

    resolveInitial({ items: [item('stale', '2026-08-10T12:00:00Z')] });
    await first;
    expect(facade.items()[0]?.id).toBe('newer');
  });

  it('starts polling once and stops late commits', async () => {
    vi.useFakeTimers();
    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.listCalls).toBe(1);

    facade.stopPolling();
    await vi.advanceTimersByTimeAsync(300);
    expect(api.listCalls).toBe(1);
    vi.useRealTimers();
  });

  it('preserves ready data when background refresh fails', async () => {
    await facade.refresh({ initial: true });
    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.items()).toHaveLength(1);
    expect(facade.error()).toContain('Showing last loaded items');
  });

  it('preserves ready data when remount polling fails immediately', async () => {
    vi.useFakeTimers();
    await facade.refresh({ initial: true });
    const preserved = facade.items();
    api.failure = true;
    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(facade.status()).toBe('ready');
    expect(facade.items()).toEqual(preserved);
    expect(facade.error()).toContain('Showing last loaded items');
    facade.stopPolling();
    vi.useRealTimers();
  });

  it('updates lastFetchedAt on committed success', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-11T12:00:00Z'));
    await facade.refresh({ initial: true });
    const first = facade.lastFetchedAt();
    vi.setSystemTime(new Date('2026-08-11T12:01:00Z'));
    await facade.refresh();
    expect(facade.lastFetchedAt()).not.toBe(first);
    vi.useRealTimers();
  });
});

class MockApi implements MediaStackApi {
  setLibraryItemPlayed = mediaStackLibraryMutationStub.setLibraryItemPlayed;
  previewLibraryItemDeletion = mediaStackLibraryMutationStub.previewLibraryItemDeletion;
  deleteLibraryItem = mediaStackLibraryMutationStub.deleteLibraryItem;
  result: { items: RecentlyAvailableItem[] } = {
    items: [item('ep-1', '2026-08-11T12:00:00Z')],
  };
  failure = false;
  nextResponse?: Promise<{ items: RecentlyAvailableItem[] }>;
  listCalls = 0;
  lastLimit?: number;

  listRecentlyAvailable(limit?: number): Promise<{ items: RecentlyAvailableItem[] }> {
    this.listCalls += 1;
    this.lastLimit = limit;
    if (this.nextResponse) return this.nextResponse;
    return this.failure
      ? Promise.reject(new Error('offline'))
      : Promise.resolve({ items: [...this.result.items] });
  }

  listTorrents() { return Promise.resolve([]); }
  pauseAll() { return Promise.resolve(); }
  resumeAll() { return Promise.resolve(); }
  pauseTorrent() { return Promise.resolve(); }
  resumeTorrent() { return Promise.resolve(); }
  listCalendarEvents() { return Promise.resolve([]); }
  getArrLibrary() { return Promise.resolve({ ok: true, series: {}, movies: {} }); }
  listLibraryItems() { return Promise.resolve({ items: [], availability: 'complete' as const }); }
  listWatchNext() { return Promise.resolve({ items: [] }); }
  getActivity() {
    return Promise.resolve({
      ok: true,
      generatedAt: '',
      sources: { sonarr: 'ok' as const, radarr: 'ok' as const },
      items: [],
    });
  }
  getLibraryStats() { return Promise.resolve({ movies: 0, series: 0, availability: 'complete' as const }); }
  getStorageOverview() { return Promise.resolve({ generatedAt: '', volumes: [] }); }
  getAutomationSummary() {
    return Promise.resolve({
      generatedAt: '',
      services: [],
      preview: [],
      problems: [],
      availability: { services: 'empty' as const, preview: 'empty' as const, problems: 'empty' as const },
    });
  }
  listCronLogs() { return Promise.resolve({ ok: true, runs: [] }); }
  listHermesRecommendations() { return Promise.resolve({ ok: true, items: [] }); }
  submitHermesFeedback() { return Promise.resolve({ ok: true }); }
  requestHermesMore() { return Promise.resolve({ ok: true }); }
  listJellyseerrDiscover() { return Promise.resolve({ ok: true, items: [] }); }
  listTraktDiscover() { return Promise.resolve({ ok: true, items: [] }); }
  requestMedia() { return Promise.resolve({ ok: true }); }
}
