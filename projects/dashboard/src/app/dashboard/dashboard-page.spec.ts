import { ComponentFixture, TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { groupCalendarEvents } from '../calendar/calendar-format';
import { vi } from 'vitest';
import { formatRelativeTime } from '../automation/automation-format';
import { AutomationFacade, AutomationStatus } from '../automation/automation.facade';
import { ServiceHealthFacade, ServiceHealthStatus } from '../automation/service-health.facade';
import { CalendarFacade, CalendarRailEvent, CalendarStatus } from '../calendar/calendar.facade';
import { DownloadsAction, DownloadsFacade, DownloadsStatus } from '../downloads/downloads.facade';
import { DownloadTorrent } from '../downloads/downloads.models';
import { LibraryStatsFacade, LibraryStatsStatus } from '../library/library-stats.facade';
import { LibraryItemsFacade, LibraryItemsStatus } from '../library/library-items.facade';
import { LibraryItem, LibraryStats } from '../library/library.models';
import { StorageFacade, StorageStatus } from '../storage/storage.facade';
import { StorageOverview } from '../storage/storage.models';
import { CronRun } from '../reports/reports.models';
import { AutomationSummary, summarizeAutomationHealth } from '../automation/automation.models';
import { fixtureHost } from '../../testing/fixture-host';
import { DashboardPage } from './dashboard-page';

describe('DashboardPage composition', () => {
  let fixture: ComponentFixture<DashboardPage>;
  let health: ReturnType<typeof createServiceHealthFacade>;
  let library: ReturnType<typeof createLibraryStatsFacade>;
  let libraryItems: ReturnType<typeof createLibraryItemsFacade>;
  let downloads: ReturnType<typeof createDownloadsFacade>;
  let automation: ReturnType<typeof createAutomationFacade>;
  let calendar: ReturnType<typeof createCalendarFacade>;
  let storage: ReturnType<typeof createStorageFacade>;

  beforeEach(() => {
    health = createServiceHealthFacade();
    library = createLibraryStatsFacade();
    libraryItems = createLibraryItemsFacade();
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
        { provide: LibraryItemsFacade, useValue: libraryItems },
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

  it('composes pagehead, metrics, and dashboard cards', () => {
    setReady();
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.pagehead h1')?.textContent).toContain('Dashboard');
    expect(root.querySelector('.pagehead')?.textContent).toMatch(/download.? active/);
    expect(root.querySelector('.metrics-row')).toBeTruthy();
    expect(root.querySelector('mm-attention-banner')).toBeNull();

    const grid = root.querySelector('[data-testid="dashboard-grid"]');
    expect(grid).toBeTruthy();

    const regions = Array.from(root.querySelectorAll('[data-region]')).map(
      (node) => node.getAttribute('data-region'),
    );
    expect(regions).toEqual(['library', 'upcoming', 'downloads', 'automation']);

    expect(root.querySelector('#library-heading')?.textContent).toContain('Library');
    expect(root.querySelector('#upcoming-heading')?.textContent).toContain('Upcoming');
    expect(root.querySelector('#downloads-heading')?.textContent).toContain('Downloads');
    expect(root.querySelector('#automation-heading')?.textContent).toContain('Connected services');
  });

  it('declares a twelve-column dashboard grid with card spans', () => {
    fixture.detectChanges();
    const styles = dashboardStyles();

    expect(styles).toContain('grid-template-columns: repeat(12, minmax(0, 1fr))');
    expect(styles).toContain('grid-column: span 8');
    expect(styles).toContain('grid-column: span 4');
    expect(styles).toContain('grid-column: span 7');
    expect(styles).toContain('grid-column: span 5');
    expect(styles).toContain('container-type: inline-size');
    expect(styles).toContain('gap: 18px');
  });

  it('collapses the grid to full-width cards on smaller viewports', () => {
    fixture.detectChanges();
    const styles = dashboardStyles();
    expect(styles).toContain('@container (max-width: 959px)');
    expect(styles).toMatch(/@container \(max-width: 959px\)[\s\S]*grid-column:\s*span 12;/);
    expect(styles).toContain('@container (max-width: 639px)');
  });

  it('keeps other regions usable when one feature fails', () => {
    library.status.set('error');
    library.error.set('Library stats offline');
    libraryItems.status.set('ready');
    health.status.set('ready');
    health.summary.set({
      generatedAt: new Date().toISOString(),
      services: [{ id: 'jellyfin', name: 'Jellyfin', status: 'healthy', detail: '', latencyMs: 10 }],
      problems: [],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'empty' },
    });
    downloads.status.set('ready');
    downloads.torrents.set([torrent()]);
    automation.status.set('ready');
    calendar.status.set('empty');
    storage.status.set('ready');
    storage.overview.set(storageOverview());
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.metrics-row')?.textContent).toContain('Library');
    expect(root.querySelector('.metrics-row')?.textContent).toContain('—');
    expect(root.querySelector('[data-region="downloads"]')).toBeTruthy();
    expect(root.querySelector('[data-region="upcoming"]')).toBeTruthy();
    expect(root.querySelector('[data-region="automation"]')).toBeTruthy();
    expect(root.querySelector('[data-testid="dashboard-grid"]')).toBeTruthy();
  });

  it('shows shimmer skeletons in the metrics row while the dashboard gate is active', () => {
    library.status.set('loading');
    libraryItems.status.set('loading');
    downloads.status.set('loading');
    health.status.set('loading');
    storage.status.set('loading');
    calendar.status.set('loading');
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const metrics = root.querySelector('.metrics-row');
    expect(metrics?.querySelectorAll('mm-skeleton').length).toBeGreaterThan(0);
    expect(metrics?.querySelectorAll('.metric-card--skeleton')).toHaveLength(4);
    expect(metrics?.textContent).not.toMatch(/0 downloads active/);
    expect(metrics?.textContent).not.toMatch(/0\s*\/\s*0/);
  });

  it('keeps metric skeletons until all core facades leave loading', () => {
    library.status.set('ready');
    library.stats.set({ movies: 12, series: 3, availability: 'complete' });
    libraryItems.status.set('ready');
    health.status.set('ready');
    health.summary.set({
      generatedAt: new Date().toISOString(),
      services: [{ id: 'jellyfin', name: 'Jellyfin', status: 'healthy', detail: '', latencyMs: 10 }],
      problems: [],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'empty' },
    });
    storage.status.set('ready');
    storage.overview.set(storageOverview());
    calendar.status.set('ready');
    downloads.status.set('loading');
    fixture.detectChanges();

    const metrics = fixtureHost(fixture).querySelector('.metrics-row');
    expect(metrics?.querySelectorAll('.metric-card--skeleton')).toHaveLength(4);
    expect(fixture.componentInstance.isLoading()).toBe(true);
  });

  it('exposes coordinated card reveal markup while the dashboard gate is active', () => {
    library.status.set('loading');
    libraryItems.status.set('loading');
    downloads.status.set('loading');
    health.status.set('loading');
    storage.status.set('loading');
    calendar.status.set('loading');
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('[data-testid="library-card"] .card__skeleton')).toBeTruthy();
    expect(root.querySelector('[data-testid="library-card"] .card__chrome-skeleton')).toBeTruthy();
    expect(root.querySelector('[data-testid="library-card"] .card__foot-skeleton')).toBeTruthy();
    expect(root.querySelector('[data-testid="library-card"] .card__inner')).toBeTruthy();
  });

  it('shows ready card content when a sibling facade is still loading (D2)', () => {
    library.status.set('loading');
    library.stats.set(null);
    libraryItems.status.set('loading');
    // Health is ready with data
    health.status.set('ready');
    health.summary.set({
      generatedAt: new Date().toISOString(),
      services: [{ id: 'jellyfin', name: 'Jellyfin', status: 'healthy', detail: '', latencyMs: 10 }],
      problems: [],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'empty' },
    });
    downloads.status.set('ready');
    downloads.torrents.set([torrent()]);
    downloads.summary.set({ active: 1, total: 1, downloaded: 50, size: 100, downloadRate: 10, uploadRate: 2 });
    automation.status.set('ready');
    automation.tasks.set([cronRun()]);
    calendar.status.set('empty');
    storage.status.set('ready');
    storage.overview.set(storageOverview());
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    // Library is loading — its skeleton content must be visible (not display:none)
    const libSkeletonMain = root.querySelector('[data-testid="library-card"] .card__skeleton-main');
    expect(libSkeletonMain).toBeTruthy();
    expect(window.getComputedStyle(libSkeletonMain as HTMLElement).display).toBe('grid');
    // Health is ready — its content should not be hidden
    const healthCard = root.querySelector('[data-testid="automation-card"]');
    expect(healthCard?.textContent).toContain('Connected services');
    expect(healthCard?.textContent).toContain('Jellyfin');
    // Downloads is ready — its torrent list should be visible
    expect(root.querySelector('[data-testid="downloads-card"] .torrent-list')).toBeTruthy();
    // The grid itself is always rendered
    expect(root.querySelector('[data-testid="dashboard-grid"]')).toBeTruthy();
  });

  it('shows error state in one card while another card is still loading (D2)', () => {
    library.status.set('loading');
    libraryItems.status.set('loading');
    // Downloads hits error while library loads
    downloads.status.set('error');
    downloads.error.set('Connection lost');
    health.status.set('ready');
    health.summary.set({
      generatedAt: new Date().toISOString(),
      services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: '', latencyMs: 12 }],
      problems: [],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'empty' },
    });
    automation.status.set('ready');
    automation.tasks.set([cronRun()]);
    calendar.status.set('empty');
    storage.status.set('ready');
    storage.overview.set(storageOverview());
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const libSkeletonMain = root.querySelector('[data-testid="library-card"] .card__skeleton-main');
    expect(libSkeletonMain).toBeTruthy();
    expect(window.getComputedStyle(libSkeletonMain as HTMLElement).display).toBe('grid');
    expect(root.querySelector('[data-testid="downloads-card"] mm-state-card')?.textContent).toContain('Connection lost');
  });

  it('keeps card region headings visible while its facade is loading (D3)', () => {
    library.status.set('loading');
    library.stats.set(null);
    libraryItems.status.set('loading');
    // Other facades ready so the class-based loader is irrelevant
    health.status.set('loading');
    downloads.status.set('loading');
    automation.status.set('ready');
    automation.tasks.set([cronRun()]);
    calendar.status.set('empty');
    storage.status.set('ready');
    storage.overview.set(storageOverview());
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    // The h2 that labels the card via aria-labelledby must not be hidden
    const heading = root.querySelector('#library-heading');
    expect(heading).toBeTruthy();
    expect(heading?.classList.contains('card__heading')).toBe(true);
    expect(window.getComputedStyle(heading as HTMLElement).visibility).not.toBe('hidden');
  });

  it('clears the dashboard loading gate when core facades are ready', () => {
    setReady();
    libraryItems.status.set('ready');
    fixture.detectChanges();
    expect(fixture.componentInstance.isLoading()).toBe(false);
  });

  it('renders regions immediately without an entrance animation', () => {
    fixture.detectChanges();
    const styles = dashboardStyles();
    expect(styles).not.toMatch(/@keyframes[\s\S]*region-enter/);
    expect(styles).not.toContain('animation: region-enter');
    expect(fixtureHost(fixture).querySelectorAll('.region')).toHaveLength(4);
  });

  it('falls back syncedAt to lastFetchedAt when generatedAt is empty', () => {
    setReady();
    health.summary.set({
      generatedAt: '',
      services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: '', latencyMs: 10 }],
      problems: [],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'empty' },
    });
    storage.overview.set({
      generatedAt: '',
      volumes: storageOverview().volumes,
    });
    health.lastFetchedAt.set('2026-07-22T11:00:00Z');
    library.lastFetchedAt.set('');
    downloads.lastFetchedAt.set('');
    storage.lastFetchedAt.set('');
    calendar.lastFetchedAt.set('');
    automation.lastFetchedAt.set('');
    fixture.detectChanges();

    expect(fixture.componentInstance.syncedAt()).toBe(formatRelativeTime('2026-07-22T11:00:00Z'));
  });

  it('refreshes all dashboard facades from onRefresh', () => {
    setReady();
    fixture.detectChanges();
    fixture.componentInstance.onRefresh();
    expect(health.refresh).toHaveBeenCalled();
    expect(library.refresh).toHaveBeenCalled();
    expect(downloads.refresh).toHaveBeenCalled();
    expect(storage.refresh).toHaveBeenCalled();
    expect(calendar.refresh).toHaveBeenCalled();
    expect(automation.refresh).toHaveBeenCalled();
  });

  it('prefers health generatedAt over a newer health lastFetchedAt', () => {
    setReady();
    health.summary.set({
      generatedAt: '2026-07-22T12:00:00Z',
      services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: '', latencyMs: 10 }],
      problems: [],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'empty' },
    });
    storage.overview.set({
      generatedAt: '2026-07-22T09:00:00Z',
      volumes: storageOverview().volumes,
    });
    health.lastFetchedAt.set('2026-07-22T12:30:00Z');
    library.lastFetchedAt.set('2026-07-22T11:00:00Z');
    downloads.lastFetchedAt.set('2026-07-22T11:15:00Z');
    storage.lastFetchedAt.set('2026-07-22T09:30:00Z');
    automation.lastFetchedAt.set('2026-07-22T11:30:00Z');
    calendar.lastFetchedAt.set('2026-07-22T11:45:00Z');
    fixture.detectChanges();

    expect(fixture.componentInstance.syncedAt()).toBe(formatRelativeTime('2026-07-22T12:00:00Z'));
  });

  it('prefers the newest freshness timestamp across dashboard facades', () => {
    setReady();
    health.summary.set({
      generatedAt: '2026-07-22T10:00:00Z',
      services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: '', latencyMs: 10 }],
      problems: [],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'empty' },
    });
    storage.overview.set({
      generatedAt: '2026-07-22T09:00:00Z',
      volumes: storageOverview().volumes,
    });
    health.lastFetchedAt.set('2026-07-22T10:30:00Z');
    library.lastFetchedAt.set('2026-07-22T11:00:00Z');
    downloads.lastFetchedAt.set('2026-07-22T11:15:00Z');
    storage.lastFetchedAt.set('2026-07-22T09:30:00Z');
    automation.lastFetchedAt.set('2026-07-22T11:30:00Z');
    calendar.lastFetchedAt.set('2026-07-22T12:00:00Z');
    fixture.detectChanges();

    expect(fixture.componentInstance.syncedAt()).toBe(formatRelativeTime('2026-07-22T12:00:00Z'));
  });

  function setReady(): void {
    health.status.set('ready');
    libraryItems.status.set('ready');
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
    library.stats.set({ movies: 428, series: 76, availability: 'complete' });
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
    .map((node) => node.textContent)
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
  const lastFetchedAt = signal('');
  return {
    status: signal<ServiceHealthStatus>('loading'),
    summary,
    services: computed(() => summary()?.services ?? []),
    problems: computed(() => summary()?.problems ?? []),
    generatedAt: computed(() => summary()?.generatedAt ?? ''),
    lastFetchedAt,
    health: computed(() => {
      const current = summary();
      return current
        ? summarizeAutomationHealth(current)
        : { overall: 'unknown' as const, actionableCount: 0 };
    }),
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
    availability: signal<'complete' | 'partial'>('complete'),
    refreshing: signal(false),
    lastFetchedAt: signal(''),
    refresh: vi.fn(),
  };
}

function createLibraryItemsFacade() {
  return {
    status: signal<LibraryItemsStatus>('loading'),
    items: signal<LibraryItem[]>([]),
    error: signal(''),
    availability: signal<'complete' | 'partial'>('complete'),
    refreshing: signal(false),
    lastFetchedAt: signal(''),
    movieCount: signal(0),
    seriesCount: signal(0),
    totalCount: signal(0),
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
    lastFetchedAt: signal(''),
    startPolling: vi.fn(),
    stopPolling: vi.fn(),
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
    lastFetchedAt: signal(''),
    startPolling: vi.fn(),
    stopPolling: vi.fn(),
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
    lastFetchedAt: signal(''),
    startPolling: vi.fn(),
    stopPolling: vi.fn(),
    refresh: vi.fn(),
  };
}

function createStorageFacade() {
  const overview = signal<StorageOverview | null>(null);
  return {
    status: signal<StorageStatus>('loading'),
    overview,
    volumes: computed(() => overview()?.volumes ?? []),
    generatedAt: computed(() => overview()?.generatedAt ?? ''),
    error: signal(''),
    lastFetchedAt: signal(''),
    startPolling: vi.fn(),
    stopPolling: vi.fn(),
    refresh: vi.fn(),
  };
}
