import { ComponentFixture, TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { groupCalendarEvents } from '../calendar/calendar-format';
import { vi } from 'vitest';
import { AutomationFacade, AutomationStatus } from '../automation/automation.facade';
import { CalendarFacade, CalendarRailEvent, CalendarStatus } from '../calendar/calendar.facade';
import { DownloadsAction, DownloadsFacade, DownloadsStatus } from '../downloads/downloads.facade';
import { DownloadTorrent, LibraryItem, DEFAULT_LIBRARY_ART } from '../downloads/media-stack-api';
import { LibraryFacade, LibraryStatus } from '../library/library.facade';
import { DashboardPage } from './dashboard-page';

describe('DashboardPage composition', () => {
  let fixture: ComponentFixture<DashboardPage>;
  let library: ReturnType<typeof createLibraryFacade>;
  let downloads: ReturnType<typeof createDownloadsFacade>;
  let automation: ReturnType<typeof createAutomationFacade>;
  let calendar: ReturnType<typeof createCalendarFacade>;

  beforeEach(() => {
    library = createLibraryFacade();
    downloads = createDownloadsFacade();
    automation = createAutomationFacade();
    calendar = createCalendarFacade();

    TestBed.configureTestingModule({
      imports: [DashboardPage],
    });
    TestBed.overrideComponent(DashboardPage, {
      set: {
        providers: [
          { provide: LibraryFacade, useValue: library },
          { provide: DownloadsFacade, useValue: downloads },
          { provide: AutomationFacade, useValue: automation },
          { provide: CalendarFacade, useValue: calendar },
        ],
      },
    });
    fixture = TestBed.createComponent(DashboardPage);
  });

  it('composes library, operations, and calendar in the asymmetric grid', () => {
    library.status.set('ready');
    library.items.set([libraryItem()]);
    downloads.status.set('ready');
    downloads.torrents.set([torrent()]);
    automation.status.set('ready');
    calendar.status.set('ready');
    calendar.events.set([calendarEvent()]);
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const grid = root.querySelector('[data-testid="home-grid"]');
    expect(grid).toBeTruthy();

    const regions = Array.from(root.querySelectorAll('[data-region]')).map(
      (node) => node.getAttribute('data-region'),
    );
    expect(regions).toEqual(['library', 'calendar', 'downloads', 'automation']);

    expect(root.querySelector('#library-heading')?.textContent).toContain('Library');
    expect(root.querySelector('#downloads-heading')?.textContent).toContain('Downloads');
    expect(root.querySelector('#automation-heading')?.textContent).toContain('Automation');
    expect(root.querySelector('#calendar-heading')?.textContent).toContain('Upcoming');
    expect(root.textContent).toContain('Dune');
    expect(root.textContent).toContain('Signal Drift');
    expect(root.textContent).toContain('Cowboy Bebop');
  });

  it('declares asymmetric grid areas, sticky calendar rail, and container queries', () => {
    fixture.detectChanges();
    const styles = dashboardStyles();

    expect(styles).toContain('grid-template-columns: repeat(12, minmax(0, 1fr))');
    expect(styles).toContain('grid-column: 1/span 8');
    expect(styles).toContain('grid-column: 9/span 4');
    expect(styles).toContain('container-type: inline-size');
    expect(styles).toContain('.home-grid__downloads');
    expect(styles).toContain('.home-grid__automation');
    expect(styles).toContain('.home-grid__calendar');
    expect(styles).toContain('align-items: stretch');
    expect(styles).toContain('gap: 20px');
  });

  it('matches DOM focus order to the visual layout and collapses before tracks shrink', () => {
    fixture.detectChanges();
    const styles = dashboardStyles();
    const regions = Array.from(
      fixture.nativeElement.querySelectorAll('[data-region]') as NodeListOf<HTMLElement>,
    ).map((node) => node.getAttribute('data-region'));
    expect(regions).toEqual(['library', 'calendar', 'downloads', 'automation']);
    expect(styles).toContain('@media (max-width: 1279px)');
    expect(styles).toMatch(/@media \(max-width: 1279px\)[\s\S]*grid-column:\s*1;/);
  });

  it('keeps other regions usable when one feature fails', () => {
    library.status.set('error');
    library.error.set('Library offline');
    downloads.status.set('ready');
    downloads.torrents.set([torrent()]);
    automation.status.set('ready');
    calendar.status.set('empty');
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('[data-region="library"]')?.textContent).toContain('Library offline');
    expect(root.querySelector('[data-region="downloads"]')?.textContent).toContain('Signal Drift');
    expect(root.querySelector('[data-region="automation"]')?.textContent).toContain('Automation');
    expect(root.querySelector('[data-region="calendar"]')?.textContent).toContain('Nothing upcoming');
    expect(root.querySelector('[data-testid="home-grid"]')).toBeTruthy();
  });

  it('keeps the grid unambiguous when a feature is empty', () => {
    library.status.set('empty');
    downloads.status.set('empty');
    automation.status.set('empty');
    calendar.status.set('ready');
    calendar.events.set([calendarEvent()]);
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelectorAll('[data-region]')).toHaveLength(4);
    expect(root.querySelector('[data-region="library"]')?.textContent).toContain('Nothing here');
    expect(root.querySelector('[data-region="downloads"]')?.textContent).toContain('No active downloads');
    expect(root.querySelector('[data-region="calendar"]')?.textContent).toContain('Cowboy Bebop');
  });

  it('renders regions immediately without an entrance animation', () => {
    fixture.detectChanges();
    const styles = dashboardStyles();
    expect(styles).not.toMatch(/@keyframes[\s\S]*region-enter/);
    expect(styles).not.toContain('animation: region-enter');
    expect(fixture.nativeElement.querySelectorAll('.region').length).toBeGreaterThanOrEqual(4);
  });
});

function dashboardStyles(): string {
  return Array.from(document.querySelectorAll('style'))
    .map((node) => node.textContent ?? '')
    .join('\n');
}

function libraryItem(): LibraryItem {
  return {
    id: 'jf-dune',
    title: 'Dune',
    kind: 'movie',
    meta: '2021 · Movie',
    art: DEFAULT_LIBRARY_ART,
    overview: 'Desert power.',
    href: 'https://jellyfin.example/web/index.html#!/details?id=jf-dune',
    artworkState: 'ok',
    playable: true,
  };
}

function torrent(): DownloadTorrent {
  return {
    id: 'a',
    name: 'Signal Drift',
    state: 'downloading',
    progress: 0.5,
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
    time: 'Tonight',
    kind: 'episode',
    status: 'pending',
    airDate: '2026-07-12T18:00:00Z',
    href: 'http://localhost:8989/series/cowboy-bebop',
  };
}

function createLibraryFacade() {
  const kind = signal<'movie' | 'series'>('movie');
  return {
    status: signal<LibraryStatus>('loading'),
    kind,
    items: signal<LibraryItem[]>([]),
    movieCount: signal(0),
    seriesCount: signal(0),
    error: signal(''),
    setKind: vi.fn(),
    refresh: vi.fn(),
    viewAllHref: computed(() => 'https://jellyfin.example/web/index.html#!/movies.html'),
  };
}

function createDownloadsFacade() {
  return {
    status: signal<DownloadsStatus>('loading'),
    torrents: signal<DownloadTorrent[]>([]),
    error: signal(''),
    notice: signal(''),
    pendingAction: signal<DownloadsAction | null>(null),
    summary: signal({ active: 0, total: 0, downloaded: 0, size: 0, downloadRate: 0, uploadRate: 0 }),
    startPolling: vi.fn(),
    refresh: vi.fn(),
    runAction: vi.fn(),
  };
}

function createAutomationFacade() {
  return {
    status: signal<AutomationStatus>('loading'),
    summary: signal(null),
    error: signal(''),
    health: signal({ overall: 'unknown' as const, actionableCount: 0 }),
    tasks: signal([]),
    summaryUnavailable: signal(false),
    tasksUnavailable: signal(false),
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
