import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { LucideArrowDown, LucideArrowUp, LucideDownload } from '@lucide/angular';
import { MmButton, MmCard, MmProgress, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { formatBytes, formatEta, formatRate, groupTorrents, TORRENT_STATE_VIEW } from './downloads-format';
import { DownloadsFacade } from './downloads.facade';
import { TorrentState } from './downloads.models';

@Component({
  selector: 'mm-downloads-board',
  imports: [MmButton, MmCard, MmProgress, MmSkeleton, MmStateCard, MmStatus, LucideArrowDown, LucideArrowUp, LucideDownload],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './downloads-board.html',
  styleUrl: './downloads-board.scss',
})
export class DownloadsBoard {
  readonly facade = inject(DownloadsFacade);
  readonly torrentSkeletons = [0, 1];
  readonly groups = computed(() => groupTorrents(this.facade.torrents()));
  readonly showGroupHeadings = computed(() => this.groups().length > 1);
  readonly hasActive = computed(() => this.facade.torrents().some((torrent) => torrent.state === 'downloading'));
  readonly hasPaused = computed(() => this.facade.torrents().some((torrent) => torrent.state === 'paused'));
  readonly formatBytes = formatBytes;
  readonly formatRate = formatRate;
  readonly formatEta = formatEta;

  constructor() {
    this.facade.startPolling();
  }

  stateView(state: TorrentState) {
    return TORRENT_STATE_VIEW[state];
  }

  pauseAll(): void {
    void this.facade.runAction('pause');
  }

  resumeAll(): void {
    void this.facade.runAction('resume');
  }

  retry(): void {
    void this.facade.refresh();
  }
}
