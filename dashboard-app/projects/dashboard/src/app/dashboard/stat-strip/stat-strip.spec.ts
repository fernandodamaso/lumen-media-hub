import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ServiceHealthFacade, ServiceHealthStatus } from '../../automation/service-health.facade';
import { AutomationService } from '../../automation/automation.models';
import { DownloadsFacade, DownloadsStatus } from '../../downloads/downloads.facade';
import { LibraryStatsFacade, LibraryStatsStatus } from '../../library/library-stats.facade';
import { LibraryStats } from '../../library/library.models';
import { WatchNextFacade, WatchNextStatus } from '../../library/watch-next.facade';
import { StorageFacade, StorageStatus } from '../../storage/storage.facade';
import { StorageOverview } from '../../storage/storage.models';
import { fixtureHost } from '../../../testing/fixture-host';
import { StatStrip } from './stat-strip';

const services: AutomationService[] = [
  { id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: '', latencyMs: 10 },
  { id: 'radarr', name: 'Radarr', status: 'healthy', detail: '', latencyMs: 12 },
  { id: 'jellyfin', name: 'Jellyfin', status: 'degraded', detail: 'Slow', latencyMs: 400 },
];

const overview: StorageOverview = {
  generatedAt: '',
  volumes: [{ id: 'media', label: 'Media library', kind: 'library', usedBytes: 5 * 1024 ** 3, totalBytes: 10 * 1024 ** 3 }],
};

describe('StatStrip', () => {
  const libraryStatus = signal<LibraryStatsStatus>('loading');
  const stats = signal<LibraryStats | null>(null);
  const downloadsStatus = signal<DownloadsStatus>('loading');
  const downloadsSummary = signal({ active: 0, total: 0, downloaded: 0, size: 0, downloadRate: 0, uploadRate: 0 });
  const watchNextStatus = signal<WatchNextStatus>('loading');
  const watchNextTotal = signal(0);
  const storageStatus = signal<StorageStatus>('loading');
  const storageOverview = signal<StorageOverview | null>(null);
  const healthStatus = signal<ServiceHealthStatus>('loading');
  const healthServices = signal<AutomationService[]>([]);

  beforeEach(() => {
    libraryStatus.set('ready');
    stats.set({ movies: 428, series: 76, availability: 'complete' });
    downloadsStatus.set('ready');
    downloadsSummary.set({ active: 2, total: 2, downloaded: 50, size: 100, downloadRate: 1024, uploadRate: 512 });
    watchNextStatus.set('ready');
    watchNextTotal.set(8);
    storageStatus.set('ready');
    storageOverview.set(overview);
    healthStatus.set('ready');
    healthServices.set(services);

    TestBed.configureTestingModule({
      imports: [StatStrip],
      providers: [
        provideRouter([]),
        { provide: LibraryStatsFacade, useValue: { status: libraryStatus, stats } },
        { provide: DownloadsFacade, useValue: { status: downloadsStatus, summary: downloadsSummary } },
        { provide: WatchNextFacade, useValue: { status: watchNextStatus, totalCount: watchNextTotal } },
        {
          provide: StorageFacade,
          useValue: {
            status: storageStatus,
            volumes: signal(overview.volumes),
            overview: storageOverview,
          },
        },
        { provide: ServiceHealthFacade, useValue: { status: healthStatus, services: healthServices, health: signal({ overall: 'degraded' as const, actionableCount: 1 }) } },
      ],
    });
  });

  it('renders five chips with values from the facades', () => {
    const fixture = TestBed.createComponent(StatStrip);
    fixture.detectChanges();
    const chips = fixtureHost(fixture).querySelectorAll('.stat-chip');
    expect(chips).toHaveLength(5);

    const text = fixtureHost(fixture).textContent;
    expect(text).toContain('504'); // 428 movies + 76 series
    expect(text).toContain('428 movies · 76 series');
    expect(text).toContain('Active downloads');
    expect(text).toContain('Titles queued');
    expect(text).toContain('5.0 GB');
    expect(text).toContain('50% of 10.0 GB');
    expect(text).toContain('2 / 3'); // healthy / total services
    expect(text).toContain('Degraded');
  });

  it('links chips to their destinations', () => {
    const fixture = TestBed.createComponent(StatStrip);
    fixture.detectChanges();
    const hrefs = Array.from(fixtureHost(fixture).querySelectorAll<HTMLAnchorElement>('.stat-chip')).map(
      (chip) => chip.getAttribute('href'),
    );
    expect(hrefs).toEqual(['/library', '#downloads', '/library', '/reports', '/reports']);
  });

  it('shows skeleton chips while any facade is loading', () => {
    downloadsStatus.set('loading');
    const fixture = TestBed.createComponent(StatStrip);
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    expect(root.querySelectorAll('.stat-chip--skeleton').length).toBeGreaterThan(0);
    expect(root.textContent).not.toContain('504');
  });
});
