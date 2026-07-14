import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MmButton, MmCard, MmProgress, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { formatBytes, formatEta, formatRate, TORRENT_STATE_VIEW } from './downloads-format';
import { DownloadsFacade } from './downloads.facade';
import { TorrentState } from '../media-stack/media-stack-api';

@Component({
  standalone: true,
  selector: 'mm-downloads-board',
  imports: [MmButton, MmCard, MmProgress, MmSkeleton, MmStateCard, MmStatus],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './downloads-board.html',
  styleUrl: './downloads-board.scss',
})
export class DownloadsBoard {
  readonly facade = inject(DownloadsFacade);
  readonly torrentSkeletons = [0, 1];
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
