import { TestBed } from '@angular/core/testing';
import {
  MEDIA_STACK_API,
  MediaStackApi,
  MediaStackCronLogsDto,
  MediaStackTorrentDto,
} from '../downloads/media-stack-api';
import { ReportsFacade } from './reports.facade';

const mixedLogs: MediaStackCronLogsDto = {
  ok: true,
  generatedAt: '2026-07-12T12:00:00Z',
  logs: [
    {
      id: 'watchdog',
      title: 'Watchdog',
      file: 'watchdog.ndjson',
      format: 'ndjson',
      schedule: '*/15 * * * *',
      exists: true,
      runs: [
        {
          timestamp: '2026-07-12T11:45:00Z',
          status: 'fatal',
          detail: 'Disk full',
          fatal: 'Disk full',
          exitCode: 1,
        },
        {
          timestamp: '2026-07-12T11:30:00Z',
          status: 'ok',
          detail: 'Checked 1, no repairs needed',
          exitCode: 0,
        },
      ],
    },
  ],
};

const allClearLogs: MediaStackCronLogsDto = {
  ok: true,
  generatedAt: '2026-07-12T13:00:00Z',
  logs: [
    {
      id: 'weekly-validate',
      title: 'Weekly validate',
      file: 'weekly-validate.log',
      format: 'text',
      schedule: '0 4 * * 0',
      exists: true,
      runs: [{ timestamp: '2026-07-06T04:00:00Z', status: 'ok', detail: 'Completed', exitCode: 0 }],
    },
  ],
};

describe('ReportsFacade', () => {
  let api: MockApi;
  let facade: ReportsFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [ReportsFacade, { provide: MEDIA_STACK_API, useValue: api }],
    });
    facade = TestBed.inject(ReportsFacade);
  });

  it('loads mixed, all-clear, and empty states', async () => {
    await facade.load();
    expect(facade.status()).toBe('mixed');
    expect(facade.runs()[0]?.status).toBe('fatal');
    expect(facade.summary()).toMatchObject({ kind: 'mixed', actionable: 1, quiet: 1 });
    expect(facade.generatedAt()).toBe('2026-07-12T12:00:00Z');
    expect(facade.error()).toBe('');

    api.response = allClearLogs;
    await facade.refresh();
    expect(facade.status()).toBe('allClear');
    expect(facade.summary().actionable).toBe(0);
    expect(facade.generatedAt()).toBe('2026-07-12T13:00:00Z');

    api.response = { ok: true, generatedAt: '2026-07-12T14:00:00Z', logs: [] };
    await facade.refresh();
    expect(facade.status()).toBe('empty');
    expect(facade.runs()).toEqual([]);
  });

  it('surfaces error on initial load failure with empty runs', async () => {
    api.failure = true;
    await facade.load();
    expect(facade.status()).toBe('error');
    expect(facade.runs()).toEqual([]);
    expect(facade.error()).toContain('temporarily unavailable');
  });

  it('treats soft ok:false envelopes as load/refresh failures', async () => {
    api.response = { ok: false, error: 'backend offline', logs: [] };
    await facade.load();
    expect(facade.status()).toBe('error');
    expect(facade.runs()).toEqual([]);

    api.response = structuredClone(mixedLogs);
    await facade.load();
    expect(facade.status()).toBe('mixed');

    api.response = { ok: false, error: 'backend offline', logs: [], generatedAt: '2026-07-12T99:00:00Z' };
    await facade.refresh();
    expect(facade.status()).toBe('mixed');
    expect(facade.generatedAt()).toBe('2026-07-12T12:00:00Z');
    expect(facade.error()).toContain('Showing last loaded history');
  });

  it('retains prior data when refresh fails after a successful load', async () => {
    await facade.load();
    const priorRuns = facade.runs();
    const priorGeneratedAt = facade.generatedAt();
    const priorStatus = facade.status();

    api.failure = true;
    await facade.refresh();

    expect(facade.runs()).toEqual(priorRuns);
    expect(facade.generatedAt()).toBe(priorGeneratedAt);
    expect(facade.status()).toBe(priorStatus);
    expect(facade.status()).not.toBe('error');
    expect(facade.error()).toContain('Showing last loaded history');
  });

  it('clears refresh error and updates generatedAt on successful refresh', async () => {
    await facade.load();
    api.failure = true;
    await facade.refresh();
    expect(facade.error()).toBeTruthy();

    api.failure = false;
    api.response = {
      ...allClearLogs,
      generatedAt: '2026-07-12T15:30:00Z',
    };
    await facade.refresh();
    expect(facade.error()).toBe('');
    expect(facade.generatedAt()).toBe('2026-07-12T15:30:00Z');
    expect(facade.status()).toBe('allClear');
  });
});

class MockApi implements MediaStackApi {
  response: MediaStackCronLogsDto = structuredClone(mixedLogs);
  failure = false;
  listCalls = 0;

  listTorrents(): Promise<MediaStackTorrentDto[]> {
    return Promise.resolve([]);
  }
  pauseAll(): Promise<void> {
    return Promise.resolve();
  }
  resumeAll(): Promise<void> {
    return Promise.resolve();
  }
  listCalendarEvents() {
    return Promise.resolve([]);
  }
  getArrLibrary() {
    return Promise.resolve({ ok: true, series: {}, movies: {} });
  }
  listCronLogs(): Promise<MediaStackCronLogsDto> {
    this.listCalls++;
    return this.failure ? Promise.reject(new Error('offline')) : Promise.resolve(structuredClone(this.response));
  }
}
