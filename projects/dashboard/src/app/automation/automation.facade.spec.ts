import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import {
  MEDIA_STACK_API,
  MediaStackApi,
  MediaStackArrLibraryDto,
  MediaStackAutomationSummaryDto,
  MediaStackCalendarEventDto,
  MediaStackTorrentDto,
} from '../downloads/media-stack-api';
import { AutomationFacade } from './automation.facade';

const defaultSummary: MediaStackAutomationSummaryDto = {
  generatedAt: '2026-07-12T18:00:00Z',
  services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK' }],
  preview: [{ id: 'p1', title: 'Dune', when: 'Jul 13', kind: 'movie' }],
  problems: [{ id: 'x1', summary: 'Disk low', serviceId: 'radarr', severity: 'actionable' }],
};

describe('AutomationFacade', () => {
  let api: MockApi;
  let facade: AutomationFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [AutomationFacade, { provide: MEDIA_STACK_API, useValue: api }],
    });
    facade = TestBed.inject(AutomationFacade);
  });

  it('moves from loading to ready when summary has signals', async () => {
    expect(facade.status()).toBe('loading');
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.summary()?.services).toHaveLength(1);
    expect(facade.health()).toEqual({ overall: 'healthy', actionableCount: 1 });
  });

  it('reports empty when no sections have data', async () => {
    api.summary = { generatedAt: '2026-07-12T18:00:00Z', services: [], preview: [], problems: [] };
    await facade.refresh();
    expect(facade.status()).toBe('empty');
  });

  it('reports partial when a section is unavailable', async () => {
    api.summary = { generatedAt: '2026-07-12T18:00:00Z', services: [], preview: [], problems: [], unavailable: { services: true } };
    await facade.refresh();
    expect(facade.status()).toBe('partial');
    expect(facade.summary()).not.toBeNull();
  });

  it('reports error and preserves recoverability', async () => {
    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');
    api.failure = false;
    await facade.refresh();
    expect(facade.status()).toBe('ready');
  });

  it('refreshes on one interval and stops polling when destroyed', async () => {
    vi.useFakeTimers();
    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.calls).toBe(1);
    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(200);
    expect(api.calls).toBe(3);
    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(200);
    expect(api.calls).toBe(3);
    vi.useRealTimers();
  });
});

class MockApi implements MediaStackApi {
  summary: MediaStackAutomationSummaryDto = { ...defaultSummary };
  calls = 0;
  failure = false;

  getAutomationSummary(): Promise<MediaStackAutomationSummaryDto> {
    this.calls++;
    return this.failure ? Promise.reject(new Error('offline')) : Promise.resolve({ ...this.summary });
  }

  listTorrents(): Promise<MediaStackTorrentDto[]> {
    return Promise.resolve([]);
  }
  pauseAll(): Promise<void> {
    return Promise.resolve();
  }
  resumeAll(): Promise<void> {
    return Promise.resolve();
  }
  listCalendarEvents(): Promise<MediaStackCalendarEventDto[]> {
    return Promise.resolve([]);
  }
  getArrLibrary(): Promise<MediaStackArrLibraryDto> {
    return Promise.resolve({ ok: true, series: {}, movies: {} });
  }
  listLibraryItems() {
    return Promise.resolve([]);
  }
  listCronLogs() {
    return Promise.resolve({ ok: true, logs: [] });
  }
}
