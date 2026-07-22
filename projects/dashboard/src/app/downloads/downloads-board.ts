import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { LucideArrowDown, LucideArrowUp, LucideDownload, LucideExternalLink, LucideLoaderCircle, LucidePause, LucidePlay } from '@lucide/angular';
import { MmButton, MmCard, MmProgress, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { formatBytes, formatEta, formatRate, groupTorrents, torrentArt } from './downloads-format';
import { DownloadsAction, DownloadsFacade } from './downloads.facade';

@Component({
  selector: 'mm-downloads-board',
  imports: [MmButton, MmCard, MmProgress, MmSkeleton, MmStateCard, MmStatus, LucideArrowDown, LucideArrowUp, LucideDownload, LucideExternalLink, LucideLoaderCircle, LucidePause, LucidePlay],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './downloads-board.html',
  styleUrl: './downloads-board.scss',
})
export class DownloadsBoard {
  readonly facade = inject(DownloadsFacade);
  private readonly linkBases = inject(SERVICE_LINK_BASES);
  readonly torrentSkeletons = [0, 1];
  readonly groups = computed(() => groupTorrents(this.facade.torrents()));
  readonly formatBytes = formatBytes;
  readonly formatRate = formatRate;
  readonly formatEta = formatEta;
  readonly torrentArt = torrentArt;

  constructor() {
    this.facade.startPolling();
  }

  qbittorrentHref(): string | null {
    const base = (this.linkBases).qbittorrent?.replace(/\/$/, '');
    return base ? `${base}/` : null;
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
