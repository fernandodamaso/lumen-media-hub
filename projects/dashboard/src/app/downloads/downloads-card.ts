import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { LucideArrowDown, LucideArrowUp, LucidePause, LucidePlay } from '@lucide/angular';
import { MmButton, MmIconButton, MmProgress, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { formatBytes, formatEta, formatRate, formatRateParts, groupTorrents, torrentArt, TORRENT_STATE_VIEW, StatusTone } from './downloads-format';
import { DownloadsAction, DownloadsFacade } from './downloads.facade';
import { TorrentState } from './downloads.models';

@Component({
  selector: 'mm-downloads-card',
  imports: [
    MmButton,
    MmIconButton,
    MmProgress,
    MmSkeleton,
    MmStateCard,
    MmStatus,
    LucideArrowDown,
    LucideArrowUp,
    LucidePause,
    LucidePlay,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './downloads-card.html',
  styleUrl: './downloads-card.scss',
})
export class DownloadsCard {
  readonly facade = inject(DownloadsFacade);
  private readonly linkBases = inject(SERVICE_LINK_BASES);
  readonly torrentSkeletons = [0, 1];
  readonly groups = computed(() => groupTorrents(this.facade.torrents()));
  readonly formatBytes = formatBytes;
  readonly formatRate = formatRate;
  readonly formatRateParts = formatRateParts;
  readonly formatEta = formatEta;
  readonly torrentArt = torrentArt;

  constructor() {
    this.facade.startPolling();
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
    void this.facade.runAction(action);
  }

  runTorrentAction(id: string, action: DownloadsAction): void {
    void this.facade.runTorrentAction(id, action);
  }

  retry(): void {
    void this.facade.refresh();
  }
}
