import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { Router } from '@angular/router';
import { AutomationFacade } from '../automation/automation.facade';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { CalendarFacade } from '../calendar/calendar.facade';
import { DownloadsFacade } from '../downloads/downloads.facade';
import { JELLYFIN_LINK_BASES, JellyfinLinkBases } from '../library/library.models';
import { SERVICE_LINK_BASES, ServiceLinkBases } from '../media-stack/media-stack-api.providers';
import { LibraryStatsFacade } from '../library/library-stats.facade';
import { StorageFacade } from '../storage/storage.facade';
import { AttentionBanner } from './attention-banner';
import { AutomationRunsCard } from './automation-runs-card';
import { DashboardHeader } from './dashboard-header';
import { MetricCard } from './metric-card';
import { ServiceHealthCard } from './service-health-card';
import { StorageCard } from './storage-card';
import { DownloadsBoard } from '../downloads/downloads-board';
import { CalendarBoard } from '../calendar/calendar-board';
import { formatRelativeTime } from '../automation/automation-format';
import { formatStorageBytes } from '../storage/storage-format';

@Component({
  selector: 'mm-dashboard-page',
  imports: [
    AttentionBanner,
    AutomationRunsCard,
    CalendarBoard,
    DashboardHeader,
    DownloadsBoard,
    MetricCard,
    ServiceHealthCard,
    StorageCard,
  ],
  providers: [
    CalendarFacade,
    DownloadsFacade,
    LibraryStatsFacade,
    StorageFacade,
    AutomationFacade,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard-page.html',
  styleUrl: './dashboard-page.scss',
})
export class DashboardPage {
  private readonly router = inject(Router);
  private readonly jellyfinBases = inject(JELLYFIN_LINK_BASES);
  private readonly serviceBases = inject(SERVICE_LINK_BASES);
  readonly health = inject(ServiceHealthFacade);
  readonly library = inject(LibraryStatsFacade);
  readonly downloads = inject(DownloadsFacade);
  readonly storage = inject(StorageFacade);

  readonly syncedAt = computed(() => {
    const generatedAt = this.health.generatedAt();
    return generatedAt ? formatRelativeTime(generatedAt) : 'just now';
  });

  readonly libraryTotal = computed(() => {
    const stats = this.library.stats();
    if (!stats) return '—';
    return stats.movies + stats.series;
  });

  readonly libraryMeta = computed(() => {
    const stats = this.library.stats();
    if (!stats) return null;
    // Home totals come from /jellyfin/stats (always complete). Partial availability is only for
    // unfiltered listLibraryItems aggregation, not this metric.
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
    return active === 1 ? '1 active download' : `${active} active downloads`;
  });

  readonly servicesMeta = computed(() => {
    const services = this.health.services();
    const total = services.length;
    const healthy = services.filter((service) => service.status === 'healthy').length;
    return `${healthy} / ${total} healthy`;
  });

  readonly servicesStatus = computed(() => {
    const overall = this.health.health().overall;
    return overall === 'healthy' ? 'Healthy' : overall === 'degraded' ? 'Degraded' : 'Issues';
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

  readonly attentionHeadline = computed(() => {
    const count = this.health.problems().length;
    return `${count} item${count === 1 ? '' : 's'} need attention`;
  });

  readonly attentionMessage = computed(() => {
    const down = this.health.services()
      .filter((service) => service.status === 'down')
      .map((service) => service.name);
    const degraded = this.health.services()
      .filter((service) => service.status === 'degraded')
      .map((service) => service.name);
    const parts: string[] = [];
    if (down.length) parts.push(`${down.join(', ')} ${down.length === 1 ? 'is' : 'are'} offline`);
    if (degraded.length) parts.push(`${degraded.join(', ')} ${degraded.length === 1 ? 'is' : 'are'} degraded`);
    return parts.join(' · ') || 'Some services need attention';
  });

  readonly hasAttention = computed(() => this.health.problems().length > 0 || this.health.health().overall === 'down' || this.health.health().overall === 'degraded');

  jellyfinLibraryHref(): string | null {
    const base = (this.jellyfinBases as JellyfinLinkBases).jellyfinBase?.replace(/\/$/, '');
    return base ? `${base}/web/index.html#!/movies.html` : null;
  }

  jellyfinSearchHref(query: string): string | null {
    const base = (this.jellyfinBases as JellyfinLinkBases).jellyfinBase?.replace(/\/$/, '');
    return base ? `${base}/web/index.html#!/search.html?q=${encodeURIComponent(query)}` : null;
  }

  onRequestMedia(): void {
    void this.router.navigate(['/discover']);
  }

  onOpenJellyfin(): void {
    const href = (this.jellyfinBases as JellyfinLinkBases).jellyfinBase;
    if (href) window.open(href, '_blank', 'noreferrer');
  }

  onSearch(query: string): void {
    const href = this.jellyfinSearchHref(query);
    if (href) window.open(href, '_blank', 'noreferrer');
  }

  onRefresh(): void {
    void this.health.refresh();
    void this.library.refresh();
    void this.downloads.refresh();
    void this.storage.refresh();
  }

  qbittorrentHref(): string | null {
    const base = (this.serviceBases as ServiceLinkBases).qbittorrent?.replace(/\/$/, '');
    return base ? `${base}/` : null;
  }
}
