import { ChangeDetectionStrategy, Component, computed, DestroyRef, inject } from '@angular/core';
import { MmButton, MmMediaCard, MmReveal, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { AutomationFacade } from '../../automation/automation.facade';
import { ServiceHealthFacade } from '../../automation/service-health.facade';
import { CalendarFacade } from '../../calendar/calendar.facade';
import { DownloadsAction, DownloadsFacade } from '../../downloads/downloads.facade';
import {
  formatBytes,
  formatEta,
  formatRate,
  formatRateParts,
  groupTorrents,
  StatusTone,
  torrentDisplayLabel,
  torrentDisplayTone,
} from '../../downloads/downloads-format';
import { DownloadTorrent } from '../../downloads/downloads.models';
import { LibraryItemsFacade } from '../../library/library-items.facade';
import { LibraryStatsFacade } from '../../library/library-stats.facade';
import { RecentlyAvailableFacade } from '../../library/recently-available.facade';
import { RecentlyAvailableItem } from '../../library/recently-available.models';
import {
  formatRecentlyAvailableCardSubtitle,
  isNewlyAvailable,
  recentlyAvailableLinkLabel,
} from '../../library/recently-available-format';
import { WatchNextFacade } from '../../library/watch-next.facade';
import { JELLYFIN_LINK_BASES, resolveJellyfinItemLink } from '../../library/library.models';
import { SERVICE_LINK_BASES } from '../../media-stack/media-stack-api.providers';
import { ActivityFacade } from '../../right-rail/activity.facade';
import { StorageFacade } from '../../storage/storage.facade';
import { refreshDashboardData } from '../dashboard-refresh';
import { DashboardHero } from '../dashboard-hero/dashboard-hero';
import { MmDownloadItem } from '../../downloads/download-item/download-item';
import { MediaRail } from '../media-rail/media-rail';
import { StatStrip } from '../stat-strip/stat-strip';
import { TrendingFacade } from '../trending.facade';
import { WatchNextItem } from '../../library/watch-next.models';

import { discoverPosterFallback } from '../../discover/discover-format';

const RAIL_LIMIT = 10;

@Component({
  selector: 'mm-dashboard-page',
  imports: [
    MmButton,
    MmDownloadItem,
    MmMediaCard,
    MmReveal,
    MmSkeleton,
    MmStateCard,
    MmStatus,
    DashboardHero,
    MediaRail,
    StatStrip,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard-page.html',
  styleUrl: './dashboard-page.scss',
})
export class DashboardPage {
  private readonly destroyRef = inject(DestroyRef);
  private readonly linkBases = inject(SERVICE_LINK_BASES);
  private readonly jellyfinBases = inject(JELLYFIN_LINK_BASES);
  private readonly health = inject(ServiceHealthFacade);
  private readonly libraryStats = inject(LibraryStatsFacade);
  private readonly calendar = inject(CalendarFacade);
  private readonly automation = inject(AutomationFacade);
  private readonly activity = inject(ActivityFacade);
  private readonly libraryItems = inject(LibraryItemsFacade);
  readonly watchNext = inject(WatchNextFacade);
  readonly recentlyAvailable = inject(RecentlyAvailableFacade);
  readonly trending = inject(TrendingFacade);
  readonly downloads = inject(DownloadsFacade);
  private readonly storage = inject(StorageFacade);

  readonly railSkeletons = [0, 1, 2, 3];
  readonly torrentSkeletons = [0, 1];

  readonly continueWatching = computed(() =>
    this.watchNext
      .items()
      .filter((item) => item.progressPercent > 0)
      .slice(0, RAIL_LIMIT),
  );
  readonly continueWatchingCount = computed(() => {
    const total = this.watchNext.items().filter((item) => item.progressPercent > 0).length;
    return total === 1 ? '1 in progress' : `${total} in progress`;
  });
  readonly groups = computed(() => groupTorrents(this.downloads.visibleTorrents()));

  readonly libraryNotice = computed(() => {
    if (this.libraryStats.error() && this.libraryStats.status() === 'ready') {
      return this.libraryStats.error();
    }
    return '';
  });

  readonly formatBytes = formatBytes;
  readonly formatRate = formatRate;
  readonly formatRateParts = formatRateParts;
  readonly formatEta = formatEta;

  downRateText(bytesPerSecond: number): string {
    return formatRate(bytesPerSecond);
  }

  constructor() {
    this.downloads.startPolling();
    this.recentlyAvailable.startPolling();
    this.destroyRef.onDestroy(() => {
      this.downloads.stopPolling();
      this.recentlyAvailable.stopPolling();
    });
  }

  /** Landscape card art: Jellyfin thumb when available, else the item's gradient art. */
  cardArt(item: WatchNextItem | RecentlyAvailableItem): string {
    if ('thumbUrl' in item && item.thumbUrl) {
      return item.thumbUrl.includes('gradient(') || item.thumbUrl.startsWith('url(')
        ? item.thumbUrl
        : `url("${item.thumbUrl}") center / cover no-repeat`;
    }
    return item.art;
  }

  trendingArt(item: { title: string }): string {
    return discoverPosterFallback(item.title);
  }

  trendingSub(item: { year: number | null; type: 'movie' | 'tv' }): string {
    const kind = item.type === 'movie' ? 'Film' : 'Series';
    return item.year ? `${item.year} · ${kind}` : kind;
  }

  qbittorrentHref(): string | null {
    const base = this.linkBases.qbittorrent?.replace(/\/$/, '');
    return base ? `${base}/` : null;
  }

  stateLabel(torrent: DownloadTorrent): string {
    return torrentDisplayLabel(torrent);
  }

  statePillClass(torrent: DownloadTorrent): string {
    const tone = torrentDisplayTone(torrent);
    const map: Record<StatusTone, string> = {
      info: 'pill--accent',
      success: 'pill--green',
      warning: 'pill--amber',
      danger: 'pill--danger',
    };
    return map[tone];
  }

  progressTone(torrent: DownloadTorrent): 'success' | 'info' | 'muted' {
    if (torrent.completed) return 'success';
    if (torrent.state === 'downloading') return 'info';
    return 'muted';
  }

  clearCompleted(): void {
    this.downloads.clearCompletedFromView();
  }

  runAction(action: DownloadsAction): void {
    void this.downloads.runAction(action);
  }

  runTorrentAction(id: string, action: DownloadsAction): void {
    void this.downloads.runTorrentAction(id, action);
  }

  retryDownloads(): void {
    void this.downloads.refresh();
  }

  recentlyAvailableSubtitle(item: RecentlyAvailableItem): string {
    return formatRecentlyAvailableCardSubtitle(item, new Date());
  }

  isRecentlyAvailableNew(item: RecentlyAvailableItem): boolean {
    return isNewlyAvailable(item.availableAt, new Date());
  }

  recentlyAvailableHref(item: RecentlyAvailableItem): string | null {
    return item.href ?? resolveJellyfinItemLink(item, this.jellyfinBases);
  }

  recentlyAvailableLinkLabel(item: RecentlyAvailableItem): string {
    return recentlyAvailableLinkLabel(item);
  }

  onRefresh(): void {
    void refreshDashboardData({
      health: this.health,
      libraryItems: this.libraryItems,
      libraryStats: this.libraryStats,
      watchNext: this.watchNext,
      recentlyAvailable: this.recentlyAvailable,
      downloads: this.downloads,
      storage: this.storage,
      calendar: this.calendar,
      automation: this.automation,
      activity: this.activity,
      trending: this.trending,
    });
  }

  mediaHref(item: Pick<WatchNextItem | RecentlyAvailableItem, 'href' | 'id' | 'playable'>): string | null {
    return item.href ?? resolveJellyfinItemLink(item, this.jellyfinBases);
  }
}
