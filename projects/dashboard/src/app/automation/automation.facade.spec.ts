import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { AutomationSummary } from './automation.models';
import { CronLogs } from '../reports/reports.models';
import { AutomationFacade } from './automation.facade';

const defaultSummary: AutomationSummary = {
  generatedAt: '2026-07-12T18:00:00Z',
  services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK' }],
  preview: [{ id: 'p1', title: 'Dune', when: 'Jul 13', kind: 'movie' }],
  problems: [{ id: 'x1', summary: 'Disk low', serviceId: 'radarr', severity: 'actionable' }],
  availability: { services: 'present', preview: 'present', problems: 'present' },
};

const emptySummary = (): AutomationSummary => ({
  generatedAt: '2026-07-12T18:00:00Z',
  services: [],
  preview: [],
  problems: [],
  availability: { services: 'empty', preview: 'empty', problems: 'empty' },
});

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
    api.summary = emptySummary();
    await facade.refresh();
    expect(facade.status()).toBe('empty');
  });

  it('reports ready when scheduled tasks are the only available signal', async () => {
    api.summary = emptySummary();
    api.cronLogs = {
      ok: true,
      runs: [
        {
          id: 'cleanup-1',
          jobId: 'cleanup',
          jobTitle: 'Cleanup',
          status: 'ok',
          triage: 'quiet',
          timestamp: '2026-07-14T12:00:00Z',
          detail: '',
          fatal: null,
          applied: null,
          exitCode: null,
          schedule: 'Hourly',
        },
      ],
    };
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.tasks()).toHaveLength(1);
  });

  it('reports partial when a section is unavailable', async () => {
    api.summary = {
      ...emptySummary(),
      availability: { services: 'unavailable', preview: 'empty', problems: 'empty' },
    };
    await facade.refresh();
    expect(facade.status()).toBe('partial');
    expect(facade.summary()).not.toBeNull();
  });

  it('reports error and preserves recoverability', async () => {
    api.failure = true;
    api.cronFailure = true;
    await facade.refresh();
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');
    api.failure = false;
    api.cronFailure = false;
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
  summary: AutomationSummary = { ...defaultSummary, availability: { ...defaultSummary.availability } };
  calls = 0;
  failure = false;
  cronFailure = false;
  cronLogs: CronLogs = { ok: true, runs: [] };

  getAutomationSummary(): Promise<AutomationSummary> {
    this.calls++;
    return this.failure ? Promise.reject(new Error('offline')) : Promise.resolve(structuredClone(this.summary));
  }

  listTorrents() {
    return Promise.resolve([]);
  }
  pauseAll() {
    return Promise.resolve();
  }
  resumeAll() {
    return Promise.resolve();
  }
  listCalendarEvents() {
    return Promise.resolve([]);
  }
  getArrLibrary() {
    return Promise.resolve({ ok: true, series: {}, movies: {} });
  }
  listLibraryItems() {
    return Promise.resolve([]);
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
    return this.cronFailure
      ? Promise.reject(new Error('offline'))
      : Promise.resolve(structuredClone(this.cronLogs));
  }
}
