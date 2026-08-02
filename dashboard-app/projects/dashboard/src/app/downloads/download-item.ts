import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { LucideArrowDown, LucideArrowUp, LucidePause, LucidePlay } from '@lucide/angular';
import { MmIconButton, MmProgress } from '@app/ui';
import { TorrentState } from './downloads.models';

@Component({
  selector: 'mm-download-item',
  imports: [MmIconButton, MmProgress, LucideArrowDown, LucideArrowUp, LucidePause, LucidePlay],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="dl-item"
      [class.dl-item--seeding]="state() === 'seeding'"
      [class.dl-item--paused]="state() === 'paused'"
      [class.dl-item--queued]="state() === 'queued'"
      [class.dl-item--checking]="state() === 'checking'"
      [class.dl-item--error]="state() === 'error'"
    >
      <div class="dl-item__top">
        <span class="dl-item__name">
          {{ name() }}
          <span class="tag">{{ category() }}</span>
        </span>
        <span class="dl-item__state">
          @if (state() !== 'seeding') {
            <mm-icon-button
              [label]="(state() === 'paused' ? 'Resume' : 'Pause') + ' ' + name()"
              [disabled]="actionDisabled()"
              [busy]="actionBusy()"
              (click)="actionToggle.emit()"
            >
              @if (state() === 'paused') {
                <svg lucidePlay [size]="14" aria-hidden="true"></svg>
              } @else {
                <svg lucidePause [size]="14" aria-hidden="true"></svg>
              }
            </mm-icon-button>
          }
          <span class="pill" [class]="pillClass()">{{ stateLabel() }}</span>
          <span class="num num--pct">{{ progress() }}%</span>
        </span>
      </div>
      <mm-progress
        [value]="progress()"
        [showLabel]="false"
        [label]="name() + ' progress'"
        [tone]="progressTone()"
        [live]="state() === 'downloading'"
      />
      <div class="dl-item__meta">
        <span>{{ downloadedLabel() }} / {{ sizeLabel() }}</span>
        <span class="meta-rates">
          <span class="meta-rate"><svg lucideArrowDown [size]="12" aria-hidden="true"></svg> {{ downloadRateLabel() }}</span>
          <span class="meta-rate"><svg lucideArrowUp [size]="12" aria-hidden="true"></svg> {{ uploadRateLabel() }}</span>
          <span>{{ etaLabel() }}</span>
        </span>
      </div>
    </div>
  `,
  styleUrl: './download-item.scss',
})
export class MmDownloadItem {
  readonly name = input.required<string>();
  readonly category = input('Uncategorized');
  readonly state = input<TorrentState>('queued');
  readonly progress = input(0);
  readonly stateLabel = input('');
  readonly pillClass = input('');
  readonly progressTone = input<'success' | 'info' | 'muted'>('info');
  readonly downloadedLabel = input('');
  readonly sizeLabel = input('');
  readonly downloadRateLabel = input('');
  readonly uploadRateLabel = input('');
  readonly etaLabel = input('—');
  readonly actionDisabled = input(false);
  readonly actionBusy = input(false);
  readonly actionToggle = output();
}
