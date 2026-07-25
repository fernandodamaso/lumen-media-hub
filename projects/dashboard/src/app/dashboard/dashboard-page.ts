import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { Router } from '@angular/router';
import { MmButton } from '@app/ui';
import { AutomationFacade } from '../automation/automation.facade';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { CalendarFacade } from '../calendar/calendar.facade';
import { UpcomingCard } from '../calendar/upcoming-card';
import { DownloadsFacade } from '../downloads/downloads.facade';
import { DownloadsCard } from '../downloads/downloads-card';
import { JELLYFIN_LINK_BASES } from '../library/library.models';
import { LibraryCard } from '../library/library-card';
import { LibraryItemsFacade } from '../library/library-items.facade';
import { LibraryStatsFacade } from '../library/library-stats.facade';
import { StorageFacade } from '../storage/storage.facade';
import { formatRelativeTime } from '../automation/automation-format';
import { formatStorageBytes } from '../storage/storage-format';
import { AutomationCard } from './automation-card';
import { refreshDashboardData } from './dashboard-refresh';
import { MetricCard } from './metric-card';

@Component({
  selector: 'mm-dashboard-page',
  imports: [
    AutomationCard,
    DownloadsCard,
    LibraryCard,
    MetricCard,
    MmButton,
    UpcomingCard,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard-page.html',
  styleUrl: './dashboard-page.scss',
})
export class DashboardPage {
  private readonly router = inject(Router);
  private readonly jellyfinBases = inject(JELLYFIN_LINK_BASES);
  readonly health = inject(ServiceHealthFacade);
  readonly library = inject(LibraryStatsFacade);
  private readonly libraryItems = inject(LibraryItemsFacade);
  readonly downloads = inject(DownloadsFacade);
  readonly storage = inject(StorageFacade);
  private readonly calendar = inject(CalendarFacade);
  private readonly automation = inject(AutomationFacade);

  readonly syncedAt = computed(() => {
    const candidates = [
      this.health.generatedAt() || this.health.lastFetchedAt(),
      this.storage.generatedAt() || this.storage.lastFetchedAt(),
      this.library.lastFetchedAt(),
      this.downloads.lastFetchedAt(),
      this.calendar.lastFetchedAt(),
      this.automation.lastFetchedAt(),
    ];
    const newest = newestIsoTimestamp(candidates);
    return newest ? formatRelativeTime(newest) : '';
  });

  readonly pageheadDate = computed(() => {
    const now = new Date();
    return now.toLocaleDateString(undefined, {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
    });
  });

  readonly libraryTotal = computed(() => {
    const stats = this.library.stats();
    if (!stats) return '—';
    return String(stats.movies + stats.series);
  });

  readonly libraryMeta = computed(() => {
    const stats = this.library.stats();
    if (!stats) return null;
    return `${stats.movies} movies · ${stats.series} series`;
  });

  readonly libraryNotice = computed(() => {
    if (this.library.error() && this.library.status() === 'ready') {
      return this.library.error();
    }
    return '';
  });

  readonly downloadsMeta = computed(() => {
    const active = this.downloads.summary().active;
    return active === 1 ? '1 download active' : `${active} downloads active`;
  });

  readonly servicesStatus = computed(() => {
    const overall = this.health.health().overall;
    if (overall === 'healthy') return 'Healthy';
    if (overall === 'degraded') return 'Degraded';
    return 'Issues';
  });

  readonly servicesValue = computed(() => {
    const services = this.health.services();
    const total = services.length;
    const healthy = services.filter((service) => service.status === 'healthy').length;
    return `${healthy} / ${total}`;
  });

  readonly storageMeta = computed(() => {
    const volumes = this.storage.volumes();
    const library = volumes.find((volume) => volume.kind === 'library');
    if (!library) return null;
    return `${formatStorageBytes(library.usedBytes)} used · ${formatStorageBytes(library.totalBytes - library.usedBytes)} free`;
  });

  readonly storagePercent = computed(() => {
    const volumes = this.storage.volumes();
    const library = volumes.find((volume) => volume.kind === 'library');
    if (!library || !library.totalBytes) return 0;
    return Math.min(100, Math.round((library.usedBytes / library.totalBytes) * 100));
  });

  jellyfinLibraryHref(): string | null {
    const base = this.jellyfinBases.jellyfinBase?.replace(/\/$/, '');
    return base ? `${base}/web/index.html#!/movies.html` : null;
  }

  onAddMedia(): void {
    void this.router.navigate(['/discover']);
  }

  onRefresh(): void {
    void refreshDashboardData({
      health: this.health,
      libraryItems: this.libraryItems,
      libraryStats: this.library,
      downloads: this.downloads,
      storage: this.storage,
      calendar: this.calendar,
      automation: this.automation,
    });
  }
}

function newestIsoTimestamp(candidates: readonly string[]): string {
  let newest = '';
  let newestMs = Number.NEGATIVE_INFINITY;
  for (const value of candidates) {
    if (!value) continue;
    const ms = Date.parse(value);
    if (Number.isNaN(ms)) continue;
    if (ms >= newestMs) {
      newestMs = ms;
      newest = value;
    }
  }
  return newest;
}
