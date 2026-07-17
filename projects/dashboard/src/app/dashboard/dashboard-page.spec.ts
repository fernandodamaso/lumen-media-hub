import { ComponentFixture, TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { groupCalendarEvents } from '../calendar/calendar-format';
import { vi } from 'vitest';
import { AutomationFacade, AutomationStatus } from '../automation/automation.facade';
import { ServiceHealthFacade, ServiceHealthStatus } from '../automation/service-health.facade';
import { CalendarFacade, CalendarRailEvent, CalendarStatus } from '../calendar/calendar.facade';
import { DownloadsAction, DownloadsFacade, DownloadsStatus } from '../downloads/downloads.facade';
import { DownloadTorrent } from '../downloads/downloads.models';
import { LibraryStatsFacade, LibraryStatsStatus } from '../library/library-stats.facade';
import { LibraryStats } from '../library/library.models';
import { StorageFacade, StorageStatus } from '../storage/storage.facade';
import { StorageOverview } from '../storage/storage.models';
import { CronRun } from '../reports/reports.models';
import { AutomationSummary } from '../automation/automation.models';
import { DashboardPage } from './dashboard-page';

describe('DashboardPage composition', () => {
  let fixture: ComponentFixture<DashboardPage>;
  let health: ReturnType<typeof createServiceHealthFacade>;
  let library: ReturnType<typeof createLibraryStatsFacade>;
  let downloads: ReturnType<typeof createDownloadsFacade>;
  let automation: ReturnType<typeof createAutomationFacade>;
  let calendar: ReturnType<typeof createCalendarFacade>;
  let storage: ReturnType<typeof createStorageFacade>;

  beforeEach(() => {
    health = createServiceHealthFacade();
    library = createLibraryStatsFacade();
    downloads = createDownloadsFacade();
    automation = createAutomationFacade();
    calendar = createCalendarFacade();
    storage = createStorageFacade();

    TestBed.configureTestingModule({
      imports: [DashboardPage],
      providers: [
        provideRouter([]),
        { provide: ServiceHealthFacade, useValue: health },
        { provide: LibraryStatsFacade, useValue: library },
      ],
    });
    TestBed.overrideComponent(DashboardPage, {
      set: {
        providers: [
          { provide: DownloadsFacade, useValue: downloads },
          { provide: AutomationFacade, useValue: automation },
          { provide: CalendarFacade, useValue: calendar },
          { provide: StorageFacade, useValue: storage },
        ],
      },
    });
    fixture = TestBed.createComponent(DashboardPage);
  });

  it('composes header, metrics, banner, and dashboard cards', () => {
    setReady();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('mm-dashboard-header')).toBeTruthy();
    expect(root.querySelector('.metrics-row')).toBeTruthy();
    expect(root.querySelector('mm-attention-banner')).toBeTruthy();

    const grid = root.querySelector('[data-testid="home-grid"]');
    expect(grid).toBeTruthy();

    const regions = Array.from(root.querySelectorAll('[data-region]')).map(
      (node) => node.getAttribute('data-region'),
    );
    expect(regions).toEqual(['downloads', 'runs', 'calendar', 'service-health', 'storage']);

    expect(root.querySelector('#downloads-heading')?.textContent).toContain('Active downloads');
    expect(root.querySelector('#runs-heading')?.textContent).toContain('Recent automation runs');
    expect(root.querySelector('#calendar-heading')?.textContent).toContain('Upcoming');
    expect(root.querySelector('#service-health-heading')?.textContent).toContain('Service health');
    expect(root.querySelector('#storage-heading')?.textContent).toContain('Storage overview');
  });

  it('declares the 3-column dashboard grid with container queries', () => {
    fixture.detectChanges();
    const styles = dashboardStyles();

    expect(styles).toContain('grid-template-columns: repeat(12, minmax(0, 1fr))');
    expect(styles).toMatch(/grid-column:\s*1\s*\/\s*span\s*5/);
    expect(styles).toMatch(/grid-column:\s*6\s*\/\s*span\s*3/);
    expect(styles).toMatch(/grid-column:\s*9\s*\/\s*span\s*4/);
    expect(styles).toContain('container-type: inline-size');
    expect(styles).toContain('gap: 20px');
  });

  it('collapses the grid to a single column on smaller viewports', () => {
    fixture.detectChanges();
    const styles = dashboardStyles();
    expect(styles).toContain('@media (max-width: 1279px)');
    expect(styles).toMatch(/@media \(max-width: 1279px\)[\s\S]*grid-column:\s*1;/);
  });

  it('keeps other regions usable when one feature fails', () => {
    library.status.set('error');
    library.error.set('Library stats offline');
    downloads.status.set('ready');
    downloads.torrents.set([torrent()]);
    automation.status.set('ready');
    calendar.status.set('empty');
    storage.status.set('ready');
    storage.overview.set(storageOverview());
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('.metrics-row')?.textContent).toContain('Library');
    expect(root.querySelector('.metrics-row')?.textContent).toContain('—');
    expect(root.querySelector('[data-region="downloads"]')?.textContent).toContain('Signal Drift');
    expect(root.querySelector('[data-region="runs"]')?.textContent).toContain('Recent automation runs');
    expect(root.querySelector('[data-region="calendar"]')?.textContent).toContain('Nothing upcoming');
    expect(root.querySelector('[data-region="service-health"]')?.textContent).toContain('Service health');
    expect(root.querySelector('[data-testid="home-grid"]')).toBeTruthy();
  });

  it('renders regions immediately without an entrance animation', () => {
    fixture.detectChanges();
    const styles = dashboardStyles();
    expect(styles).not.toMatch(/@keyframes[\s\S]*region-enter/);
    expect(styles).not.toContain('animation: region-enter');
    expect(fixture.nativeElement.querySelectorAll('.region').length).toBeGreaterThanOrEqual(5);
  });

  function setReady(): void {
    health.status.set('ready');
    health.summary.set({
      generatedAt: new Date().toISOString(),
      services: [
        { id: 'jellyfin', name: 'Jellyfin', status: 'healthy', detail: '', latencyMs: 18 },
        { id: 'prowlarr', name: 'Prowlarr', status: 'degraded', detail: '2 warnings', latencyMs: 350 },
      ],
      problems: [{ id: 'p1', summary: 'Prowlarr warning', serviceId: 'prowlarr', severity: 'actionable' }],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    library.status.set('ready');
    library.stats.set({ movies: 428, series: 76 });
    downloads.status.set('ready');
    downloads.torrents.set([torrent()]);
    downloads.summary.set({ active: 1, total: 1, downloaded: 50, size: 100, downloadRate: 10, uploadRate: 2 });
    automation.status.set('ready');
    automation.tasks.set([cronRun()]);
    calendar.status.set('ready');
    calendar.events.set([calendarEvent()]);
    storage.status.set('ready');
    storage.overview.set(storageOverview());
  }
});

function dashboardStyles(): string {
  return Array.from(document.querySelectorAll('style'))
    .map((node) => node.textContent ?? '')
    .join('\n');
}

function torrent(): DownloadTorrent {
  return {
    id: 'a',
    name: 'Signal Drift',
    state: 'downloading',
    progress: 50,
    size: 100,
    downloaded: 50,
    downloadRate: 10,
    uploadRate: 2,
    eta: 30,
    category: 'Movies',
  };
}

function calendarEvent(): CalendarRailEvent {
  return {
    id: 'ep-1',
    title: 'Cowboy Bebop',
    subtitle: 'S1E1',
    time: '18:00',
    kind: 'episode',
    status: 'pending',
    airDate: '2026-07-12T18:00:00Z',
    href: 'http://localhost:8989/series/cowboy-bebop',
  };
}

function cronRun(): CronRun {
  return {
    id: 'run-1',
    jobId: 'watchdog',
    jobTitle: 'Watchdog',
    status: 'ok',
    triage: 'quiet' as const,
    timestamp: new Date().toISOString(),
    detail: 'All services are healthy',
    fatal: null,
    applied: null,
    exitCode: null,
    schedule: 'Monitoring',
  };
}

function storageOverview(): StorageOverview {
  return {
    generatedAt: new Date().toISOString(),
    volumes: [
      { id: 'media', label: 'Media library', kind: 'library', usedBytes: 4.8 * 1024 ** 4, totalBytes: 7.2 * 1024 ** 4 },
      { id: 'downloads', label: 'Downloads', kind: 'downloads', usedBytes: 324 * 1024 ** 3, totalBytes: 1 * 1024 ** 4 },
      { id: 'cache', label: 'Cache & temp', kind: 'cache', usedBytes: 68 * 1024 ** 3, totalBytes: 500 * 1024 ** 3 },
    ],
  };
}

function createServiceHealthFacade() {
  const summary = signal<AutomationSummary | null>(null);
  return {
    status: signal<ServiceHealthStatus>('loading'),
    summary,
    services: computed(() => summary()?.services ?? []),
    problems: computed(() => summary()?.problems ?? []),
    generatedAt: computed(() => summary()?.generatedAt ?? ''),
    health: computed(() => ({ overall: 'unknown' as const, actionableCount: 0 })),
    error: signal(''),
    startPolling: vi.fn(),
    refresh: vi.fn(),
  };
}

function createLibraryStatsFacade() {
  return {
    status: signal<LibraryStatsStatus>('loading'),
    stats: signal<LibraryStats | null>(null),
    error: signal(''),
    refresh: vi.fn(),
  };
}

function createDownloadsFacade() {
  return {
    status: signal<DownloadsStatus>('loading'),
    torrents: signal<DownloadTorrent[]>([]),
    error: signal(''),
    notice: signal(''),
    pendingAction: signal<DownloadsAction | null>(null),
    pendingTorrentId: signal<string | null>(null),
    summary: signal({ active: 0, total: 0, downloaded: 0, size: 0, downloadRate: 0, uploadRate: 0 }),
    nextAction: signal<DownloadsAction | null>(null),
    canPauseAll: signal(false),
    canResumeAll: signal(false),
    startPolling: vi.fn(),
    refresh: vi.fn(),
    runAction: vi.fn(),
    runTorrentAction: vi.fn(),
  };
}

function createAutomationFacade() {
  return {
    status: signal<AutomationStatus>('loading'),
    summary: signal<AutomationSummary | null>(null),
    error: signal(''),
    health: signal({ overall: 'unknown' as const, actionableCount: 0 }),
    tasks: signal<CronRun[]>([]),
    latestRuns: signal<CronRun[]>([]),
    startPolling: vi.fn(),
    refresh: vi.fn(),
  };
}

function createCalendarFacade() {
  const events = signal<CalendarRailEvent[]>([]);
  return {
    status: signal<CalendarStatus>('loading'),
    events,
    groups: computed(() => groupCalendarEvents(events())),
    error: signal(''),
    startPolling: vi.fn(),
    refresh: vi.fn(),
  };
}

function createStorageFacade() {
  const overview = signal<StorageOverview | null>(null);
  return {
    status: signal<StorageStatus>('loading'),
    overview,
    volumes: computed(() => overview()?.volumes ?? []),
    error: signal(''),
    startPolling: vi.fn(),
    refresh: vi.fn(),
  };
}
