import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MmButton, MmCard, MmProgress, MmSkeleton, MmStateCard, MmStatus } from 'media-ui';
import { formatBytes, formatEta, formatRate, TORRENT_STATE_VIEW } from './downloads-format';
import { DownloadsFacade } from './downloads.facade';
import { TorrentState } from '../media-stack/media-stack-api';

@Component({
  standalone: true,
  selector: 'mm-downloads-board',
  imports: [MmButton, MmCard, MmProgress, MmSkeleton, MmStateCard, MmStatus],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mm-card class="downloads" labelledBy="downloads-heading">
      <div mm-card-header>
        <h2 id="downloads-heading">Downloads</h2>
      </div>
      <div mm-card-header-actions class="header-tools">
        <div class="speed"><span>Down speed</span><strong>{{ formatRate(facade.summary().downloadRate) }}</strong></div>
        <div class="speed"><span>Up speed</span><strong>{{ formatRate(facade.summary().uploadRate) }}</strong></div>
        <div class="actions" aria-label="Download controls">
          <mm-button label="Pause all" variant="quiet" [disabled]="facade.pendingAction() !== null" [busy]="facade.pendingAction() === 'pause'" (click)="pauseAll()" />
          <mm-button label="Resume all" variant="quiet" [disabled]="facade.pendingAction() !== null" [busy]="facade.pendingAction() === 'resume'" (click)="resumeAll()" />
        </div>
      </div>
      @if (facade.notice()) {
        <p class="notice" role="status" aria-live="polite"><mm-status tone="success">{{ facade.notice() }}</mm-status></p>
      }
      @if (facade.status() === 'loading') {
        <div class="download-skeleton" aria-hidden="true">
          @for (i of torrentSkeletons; track i) {
            <div class="torrent torrent--skeleton">
              <div class="torrent-head">
                <div><mm-skeleton variant="text" width="160px" height="16px" /><mm-skeleton variant="text" width="56px" /></div>
                <mm-skeleton variant="text" width="72px" />
              </div>
              <div class="progress-row"><mm-skeleton variant="text" height="6px" /></div>
              <div class="torrent-meta">
                <mm-skeleton variant="text" width="90px" />
                <mm-skeleton variant="text" width="70px" />
                <mm-skeleton variant="text" width="70px" />
                <mm-skeleton variant="text" width="60px" />
              </div>
            </div>
          }
        </div>
      } @else if (facade.status() === 'error') {
        <mm-state-card kind="error" title="Downloads unavailable" [message]="facade.error()" tone="danger"><mm-button label="Try again" (click)="retry()" /></mm-state-card>
      } @else if (facade.status() === 'empty') {
        <mm-state-card kind="empty" title="No active downloads" message="Your queue is clear. New downloads will appear here." />
      } @else {
        <div class="torrent-list" aria-live="polite">
          @for (torrent of facade.torrents(); track torrent.id) {
            <article class="torrent">
              <div class="torrent-head">
                <div>
                  <h3>{{ torrent.name }}</h3>
                  <span class="category">{{ torrent.category }}</span>
                </div>
                <mm-status [tone]="stateView(torrent.state).tone">{{ stateView(torrent.state).label }}</mm-status>
              </div>
              <div class="progress-row"><mm-progress [value]="torrent.progress" [label]="torrent.name + ' progress'" /></div>
              <div class="torrent-meta">
                <span>{{ formatBytes(torrent.downloaded) }} / {{ formatBytes(torrent.size) }}</span>
                <span>{{ formatRate(torrent.downloadRate) }} ↓</span>
                <span>{{ formatRate(torrent.uploadRate) }} ↑</span>
                <span>{{ torrent.eta ? formatEta(torrent.eta) + ' left' : 'Complete' }}</span>
              </div>
            </article>
          }
        </div>
      }
    </mm-card>
  `,
  styles: `:host { display: block; } .header-tools { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; } .speed { display: grid; gap: 2px; font-variant-numeric: tabular-nums; } .speed span { color: var(--mm-component-text-muted); font-size: var(--mm-text-xs); font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; } .speed strong { color: var(--mm-component-text-primary); font-size: var(--mm-text-md); } h2 { margin: 0; color: var(--mm-component-text-primary); font-size: var(--mm-text-lg); font-weight: 700; letter-spacing: -0.01em; } .actions { display: flex; flex-wrap: wrap; gap: 8px; } .notice { margin: 0 0 12px; } .download-skeleton { display: grid; gap: 8px; } .torrent-list { display: grid; gap: 8px; } .torrent { display: grid; gap: 10px; padding: 12px 14px; border: 1px solid var(--mm-component-border); border-radius: var(--mm-radius-md); background: var(--mm-component-raised-bg); } .torrent--skeleton { gap: 10px; } .torrent-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; } .torrent-head > div { display: flex; align-items: center; gap: 8px; min-width: 0; } h3 { margin: 0; color: var(--mm-component-text-primary); font-size: var(--mm-text-md); font-weight: 600; } .category { color: var(--mm-component-text-muted); font-size: var(--mm-text-xs); } .progress-row { display: flex; } .torrent-meta { display: flex; align-items: center; justify-content: flex-start; gap: 16px; flex-wrap: wrap; color: var(--mm-component-text-secondary); font-size: var(--mm-text-xs); font-variant-numeric: tabular-nums; } .torrent--skeleton .torrent-meta { align-items: center; } @media (max-width: 900px), (pointer: coarse) { .torrent-head > div { flex-wrap: wrap; } } @container (max-width: 560px) { .header-tools { align-items: start; } .torrent-meta { gap: 10px; } }`,
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
