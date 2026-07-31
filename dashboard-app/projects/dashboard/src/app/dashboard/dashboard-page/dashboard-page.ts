import { ChangeDetectionStrategy, Component, computed, DestroyRef, inject } from '@angular/core';
import { LucidePlay } from '@lucide/angular';
import { MmButton, MmDownloadItem, MmReveal, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
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
  TORRENT_STATE_VIEW,
} from '../../downloads/downloads-format';
import { TorrentState } from '../../downloads/downloads.models';
import {
  JELLYFIN_LINK_BASES,
  LibraryItem,
  resolveJellyfinItemLink,
} from '../../library/library.models';
import { LibraryItemsFacade } from '../../library/library-items.facade';
import { LibraryStatsFacade } from '../../library/library-stats.facade';
import { WatchNextFacade } from '../../library/watch-next.facade';
import { WatchNextItem } from '../../library/watch-next.models';
import { SERVICE_LINK_BASES } from '../../media-stack/media-stack-api.providers';
import { ActivityFacade } from '../../right-rail/activity.facade';
import { StorageFacade } from '../../storage/storage.facade';
import { refreshDashboardData } from '../dashboard-refresh';
import { DashboardHero } from '../dashboard-hero/dashboard-hero';
import { MediaRail } from '../media-rail/media-rail';
import { StatStrip } from '../stat-strip/stat-strip';
import { TrendingFacade } from '../trending.facade';
import { discoverPosterFallback } from '../../discover/discover-format';

const RAIL_LIMIT = 10;

@Component({
  selector: 'mm-dashboard-page',
  imports: [
    MmButton,
    MmDownloadItem,
    MmReveal,
    MmSkeleton,
    MmStateCard,
    MmStatus,
    DashboardHero,
    MediaRail,
    StatStrip,
    LucidePlay,
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
  readonly libraryItems = inject(LibraryItemsFacade);
  readonly watchNext = inject(WatchNextFacade);
  readonly trending = inject(TrendingFacade);
  readonly downloads = inject(DownloadsFacade);
  private readonly storage = inject(StorageFacade);

  readonly railSkeletons = [0, 1, 2, 3];
  readonly torrentSkeletons = [0, 1];

  readonly continueWatching = computed(() => this.watchNext.items().slice(0, RAIL_LIMIT));
  readonly continueWatchingCount = computed(() => {
    const total = this.watchNext.totalCount();
    return total === 1 ? '1 in progress' : `${total} in progress`;
  });
  readonly recentItems = computed(() => this.libraryItems.items().slice(0, RAIL_LIMIT));
  readonly groups = computed(() => groupTorrents(this.downloads.torrents()));

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
    // Dashboard owns downloads polling only; shell facades are polled by App.
    this.downloads.startPolling();
    this.destroyRef.onDestroy(() => {
      this.downloads.stopPolling();
    });
  }

  /** Landscape card art: Jellyfin thumb when available, else the item's gradient art. */
  cardArt(item: WatchNextItem | LibraryItem): string {
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

  stateLabel(state: TorrentState): string {
    return TORRENT_STATE_VIEW[state].label;
  }

  statePillClass(state: TorrentState): string {
    const tone = TORRENT_STATE_VIEW[state].tone;
    const map: Record<StatusTone, string> = {
      info: 'pill--accent',
      success: 'pill--green',
      warning: 'pill--amber',
      danger: 'pill--danger',
    };
    return map[tone];
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

  onRefresh(): void {
    void refreshDashboardData({
      health: this.health,
      libraryItems: this.libraryItems,
      libraryStats: this.libraryStats,
      watchNext: this.watchNext,
      downloads: this.downloads,
      storage: this.storage,
      calendar: this.calendar,
      automation: this.automation,
      activity: this.activity,
      trending: this.trending,
    });
  }

  mediaHref(item: Pick<WatchNextItem | LibraryItem, 'href' | 'id' | 'playable'>): string | null {
    return item.href ?? resolveJellyfinItemLink(item, this.jellyfinBases);
  }
}
