import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MmButton, MmProgress, MmStateCard, MmStatus } from 'media-ui';
import { DownloadsFacade } from './downloads.facade';

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
          <mm-button label="Pause all" variant="quiet" [disabled]="facade.pendingAction() !== null" [busy]="facade.pendingAction() === 'pause'" (click)="facade.runAction('pause')" />
          <mm-button label="Resume all" [disabled]="facade.pendingAction() !== null" [busy]="facade.pendingAction() === 'resume'" (click)="facade.runAction('resume')" />
        </div>
      </div>
      @if (facade.status() === 'loading') { <mm-state-card icon="◌" title="Loading downloads" message="Checking the queue…" /> }
      @else if (facade.status() === 'error') { <mm-state-card icon="!" title="Downloads unavailable" [message]="facade.error()" tone="danger"><mm-button label="Try again" (click)="facade.refresh()" /></mm-state-card> }
      @else if (facade.status() === 'empty') { <mm-state-card icon="∅" title="No active downloads" message="Your queue is clear. New downloads will appear here." /> }
      @else {
        <div class="summary" aria-label="Download summary"><div><strong>{{ facade.summary().active }}</strong><span>active</span></div><div><strong>{{ formatBytes(facade.summary().downloaded) }}</strong><span>downloaded of {{ formatBytes(facade.summary().size) }}</span></div><div><strong>{{ formatRate(facade.summary().downloadRate) }}</strong><span>download speed</span></div><div><strong>{{ formatRate(facade.summary().uploadRate) }}</strong><span>upload speed</span></div></div>
        <div class="torrent-list">
          @for (torrent of facade.torrents(); track torrent.id) { <article class="torrent"><div class="torrent-head"><div><h3>{{ torrent.name }}</h3><span class="category">{{ torrent.category }}</span></div><mm-status [tone]="torrent.state === 'downloading' ? 'info' : torrent.state === 'seeding' ? 'success' : 'warning'">{{ labelState(torrent.state) }}</mm-status></div><div class="progress-row"><mm-progress [value]="torrent.progress" [label]="torrent.name + ' progress'" /></div><div class="torrent-meta"><span>{{ formatBytes(torrent.downloaded) }} / {{ formatBytes(torrent.size) }}</span><span>{{ formatRate(torrent.downloadRate) }} ↓</span><span>{{ torrent.eta ? formatEta(torrent.eta) + ' left' : 'Complete' }}</span></div></article> }
        </div>
      }
    </section>
  `,
  styles: `:host { display: block; } .downloads { margin-top: 52px; } .section-heading { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 18px; } h2 { margin: 0; color: var(--mm-component-text-primary); font-size: 24px; } .section-copy { margin-top: 6px; color: var(--mm-component-text-secondary); font-size: 14px; } .actions { display: flex; gap: 10px; } .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; margin-bottom: 14px; overflow: hidden; border: 1px solid var(--mm-component-border); border-radius: var(--mm-radius-md); background: var(--mm-component-border); } .summary div { display: grid; gap: 5px; padding: 16px; background: var(--mm-component-card-bg); } .summary strong { color: var(--mm-component-text-primary); font-size: 18px; } .summary span, .category, .torrent-meta { color: var(--mm-component-text-muted); font-size: 12px; } .torrent-list { display: grid; gap: 10px; } .torrent { display: grid; gap: 14px; padding: 18px; border: 1px solid var(--mm-component-border); border-radius: var(--mm-radius-md); background: var(--mm-component-card-bg); } .torrent-head, .torrent-meta { display: flex; align-items: center; justify-content: space-between; gap: 14px; } h3 { margin: 0 0 4px; color: var(--mm-component-text-primary); font-size: 15px; } .progress-row { display: flex; } .torrent-meta { justify-content: flex-start; gap: 24px; } @media (max-width: 850px) { .section-heading { align-items: start; flex-direction: column; } .summary { grid-template-columns: repeat(2, 1fr); } }`,
})
export class DownloadsBoard {
  readonly facade = inject(DownloadsFacade);

  constructor() { this.facade.startPolling(); }
  formatBytes(bytes: number): string { if (!bytes) return '0 B'; const units = ['B', 'KB', 'MB', 'GB', 'TB']; const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1); return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`; }
  formatRate(bytes: number): string { return `${this.formatBytes(bytes)}/s`; }
  formatEta(seconds: number): string { const minutes = Math.floor(seconds / 60); return minutes > 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes}m`; }
  labelState(state: string): string { return state === 'downloading' ? 'Downloading' : state === 'seeding' ? 'Seeding' : state[0].toUpperCase() + state.slice(1); }
}
