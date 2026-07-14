import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MmButton, MmProgress, MmStateCard, MmStatus } from 'media-ui';
import { formatBytes, formatEta, formatRate, TORRENT_STATE_VIEW } from './downloads-format';
import { DownloadsFacade } from './downloads.facade';
import { TorrentState } from './media-stack-api';

@Component({
  standalone: true,
  selector: 'mm-downloads-board',
  imports: [MmButton, MmProgress, MmStateCard, MmStatus],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="downloads" aria-labelledby="downloads-heading">
      <div class="section-heading">
        <div><p class="eyebrow">Live activity</p><h2 id="downloads-heading">Downloads</h2><p class="section-copy">Track and control your media queue.</p></div>
        <div class="actions" aria-label="Download controls">
          <mm-button label="Pause all" variant="quiet" [disabled]="facade.pendingAction() !== null" [busy]="facade.pendingAction() === 'pause'" (click)="pauseAll()" />
          <mm-button label="Resume all" [disabled]="facade.pendingAction() !== null" [busy]="facade.pendingAction() === 'resume'" (click)="resumeAll()" />
        </div>
      </div>
      @if (facade.notice()) {
        <p class="notice" role="status" aria-live="polite"><mm-status tone="success">{{ facade.notice() }}</mm-status></p>
      }
      @if (facade.status() === 'loading') { <mm-state-card kind="loading" title="Loading downloads" message="Checking the queue…" /> }
      @else if (facade.status() === 'error') { <mm-state-card kind="error" title="Downloads unavailable" [message]="facade.error()" tone="danger"><mm-button label="Try again" (click)="retry()" /></mm-state-card> }
      @else if (facade.status() === 'empty') { <mm-state-card kind="empty" title="No active downloads" message="Your queue is clear. New downloads will appear here." /> }
      @else {
        <div class="summary" aria-label="Download summary"><div><strong>{{ facade.summary().active }}</strong><span>active</span></div><div><strong>{{ formatBytes(facade.summary().downloaded) }}</strong><span>downloaded of {{ formatBytes(facade.summary().size) }}</span></div><div><strong>{{ formatRate(facade.summary().downloadRate) }}</strong><span>download speed</span></div><div><strong>{{ formatRate(facade.summary().uploadRate) }}</strong><span>upload speed</span></div></div>
        <div class="torrent-list" aria-live="polite">
          @for (torrent of facade.torrents(); track torrent.id) {
            <article class="torrent">
              <div class="torrent-head">
                <div><h3>{{ torrent.name }}</h3><span class="category">{{ torrent.category }}</span></div>
                <mm-status [tone]="stateView(torrent.state).tone">{{ stateView(torrent.state).label }}</mm-status>
              </div>
              <div class="progress-row"><mm-progress [value]="torrent.progress" [label]="torrent.name + ' progress'" /></div>
              <div class="torrent-meta">
                <span>{{ formatBytes(torrent.downloaded) }} / {{ formatBytes(torrent.size) }}</span>
                <span>{{ formatRate(torrent.downloadRate) }} ↓</span>
                <span>{{ torrent.eta ? formatEta(torrent.eta) + ' left' : 'Complete' }}</span>
              </div>
            </article>
          }
        </div>
      }
    </section>
  `,
  styles: `:host { display: block; } .downloads { margin-top: 0; } .section-heading { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 18px; } h2 { margin: 0; color: var(--mm-component-text-primary); font-size: 24px; } .section-copy { margin-top: 6px; color: var(--mm-component-text-secondary); font-size: 14px; } .actions { display: flex; flex-wrap: wrap; gap: 10px; } .notice { margin: 0 0 14px; } .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; margin-bottom: 14px; overflow: hidden; border: 1px solid var(--mm-component-border); border-radius: var(--mm-radius-md); background: var(--mm-component-border); } .summary div { display: grid; gap: 5px; padding: 16px; background: var(--mm-component-card-bg); } .summary strong { color: var(--mm-component-text-primary); font-size: 18px; } .summary span, .category, .torrent-meta { color: var(--mm-component-text-muted); font-size: 12px; } .torrent-list { display: grid; gap: 10px; } .torrent { display: grid; gap: 14px; padding: 18px; border: 1px solid var(--mm-component-border); border-radius: var(--mm-radius-md); background: var(--mm-component-card-bg); } .torrent-head, .torrent-meta { display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; } h3 { margin: 0 0 4px; color: var(--mm-component-text-primary); font-size: 15px; } .progress-row { display: flex; } .torrent-meta { justify-content: flex-start; gap: 24px; } @container (max-width: 560px) { .section-heading { align-items: start; flex-direction: column; } .summary { grid-template-columns: repeat(2, 1fr); } .torrent-meta { gap: 12px; } } @media (max-width: 850px) { .section-heading { align-items: start; flex-direction: column; } .summary { grid-template-columns: repeat(2, 1fr); } }`,
})
export class DownloadsBoard {
  readonly facade = inject(DownloadsFacade);
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
