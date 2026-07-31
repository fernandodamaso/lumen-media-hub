import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  LucideActivity,
  LucideBookmark,
  LucideDownload,
  LucideHardDrive,
  LucideLibrary,
} from '@lucide/angular';
import { MmSkeleton } from '@app/ui';
import { ServiceHealthFacade } from '../../automation/service-health.facade';
import { DownloadsFacade } from '../../downloads/downloads.facade';
import { formatRate } from '../../downloads/downloads-format';
import { LibraryStatsFacade } from '../../library/library-stats.facade';
import { WatchNextFacade } from '../../library/watch-next.facade';
import { StorageFacade } from '../../storage/storage.facade';
import { formatStorageBytes } from '../../storage/storage-format';

@Component({
  selector: 'mm-stat-strip',
  imports: [RouterLink, MmSkeleton, LucideActivity, LucideBookmark, LucideDownload, LucideHardDrive, LucideLibrary],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './stat-strip.html',
  styleUrl: './stat-strip.scss',
})
export class StatStrip {
  private readonly library = inject(LibraryStatsFacade);
  private readonly downloads = inject(DownloadsFacade);
  private readonly watchNext = inject(WatchNextFacade);
  private readonly storage = inject(StorageFacade);
  private readonly health = inject(ServiceHealthFacade);

  readonly skeletons = [0, 1, 2, 3, 4];

  readonly loading = computed(
    () =>
      this.library.status() === 'loading' ||
      this.downloads.status() === 'loading' ||
      this.watchNext.status() === 'loading' ||
      this.storage.status() === 'loading' ||
      this.health.status() === 'loading',
  );

  readonly libraryValue = computed(() => {
    const stats = this.library.stats();
    return stats ? String(stats.movies + stats.series) : '—';
  });

  readonly librarySub = computed(() => {
    const stats = this.library.stats();
    return stats ? `${stats.movies} movies · ${stats.series} series` : '';
  });

  readonly downloadsValue = computed(() => String(this.downloads.summary().active));

  readonly downloadsSub = computed(() => {
    const summary = this.downloads.summary();
    if (!summary.active) return 'Queue clear';
    return `${formatRate(summary.downloadRate)} · ${summary.active} in progress`;
  });

  readonly watchNextValue = computed(() => String(this.watchNext.totalCount()));

  readonly storageValue = computed(() => {
    const volume = this.storage.volumes().find((entry) => entry.kind === 'library');
    return volume ? formatStorageBytes(volume.usedBytes) : '—';
  });

  readonly storageSub = computed(() => {
    const volume = this.storage.volumes().find((entry) => entry.kind === 'library');
    if (!volume || !volume.totalBytes) return '';
    const percent = Math.min(100, Math.round((volume.usedBytes / volume.totalBytes) * 100));
    return `${percent}% of ${formatStorageBytes(volume.totalBytes)}`;
  });

  readonly servicesValue = computed(() => {
    const services = this.health.services();
    const healthy = services.filter((service) => service.status === 'healthy').length;
    return `${healthy} / ${services.length}`;
  });

  readonly servicesSub = computed(() => {
    const overall = this.health.health().overall;
    if (overall === 'healthy') return 'All connected';
    if (overall === 'degraded') return 'Degraded';
    if (overall === 'down') return 'Issues';
    return 'Unknown';
  });
}
