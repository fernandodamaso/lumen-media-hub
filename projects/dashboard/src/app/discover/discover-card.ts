import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { MmButton, MmPoster, MmStatus } from 'media-ui';
import { DiscoverFeedback } from '../downloads/media-stack-api';
import {
  DiscoverCardItem,
  formatDiscoverMeta,
  posterArtFor,
  resolveRequestAction,
} from './discover-format';

const FEEDBACK_OPTIONS: { value: DiscoverFeedback; label: string }[] = [
  { value: 'liked', label: 'Liked' },
  { value: 'disliked', label: 'Disliked' },
  { value: 'watched', label: 'Watched' },
  { value: 'skipped', label: 'Skipped' },
];

@Component({
  selector: 'mm-discover-card',
  imports: [MmButton, MmPoster, MmStatus],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <article class="discover-card">
      <mm-poster [title]="item().title" [meta]="meta()" [art]="art()" />
      <div class="body">
        <div class="badges">
          @if (item().inLibrary) {
            <mm-status tone="success">In library</mm-status>
          }
          @if (item().requestState === 'requested') {
            <mm-status tone="info">Requested</mm-status>
          }
          @if (syncFailed()) {
            <mm-status tone="warning">Sync failed</mm-status>
          }
          @if (item().feedback) {
            <mm-status tone="info">{{ item().feedback }}</mm-status>
          }
        </div>
        @if (item().reason) {
          <p class="reason">{{ item().reason }}</p>
        } @else if (item().overview) {
          <p class="reason">{{ item().overview }}</p>
        }
        @if (showFeedback()) {
          <div class="feedback" role="group" [attr.aria-label]="'Feedback for ' + item().title">
            @for (option of feedbackOptions; track option.value) {
              <button
                type="button"
                class="feedback-btn"
                [attr.aria-pressed]="item().feedback === option.value"
                [disabled]="busy()"
                (click)="feedback.emit(option.value)"
              >
                {{ option.label }}
              </button>
            }
          </div>
        }
        <div class="actions">
          <span [attr.title]="requestAction().title">
            <mm-button
              [label]="requestAction().label"
              [disabled]="requestAction().disabled || busy()"
              [busy]="busy()"
              variant="quiet"
              (click)="request.emit()"
            />
          </span>
        </div>
      </div>
    </article>
  `,
  styles: `
    :host { display: block; }
    .discover-card {
      display: grid;
      gap: 12px;
      align-content: start;
    }
    .body { display: grid; gap: 10px; }
    .badges { display: flex; flex-wrap: wrap; gap: 6px; min-height: 28px; }
    .reason {
      margin: 0;
      color: var(--mm-component-text-secondary);
      font-size: 13px;
      line-height: 1.45;
      min-height: 2.9em;
    }
    .feedback { display: flex; flex-wrap: wrap; gap: 6px; }
    .feedback-btn {
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-sm);
      padding: 6px 10px;
      background: var(--mm-component-control-bg);
      color: var(--mm-component-text-primary);
      cursor: pointer;
      font: 700 12px/1 var(--mm-font-body);
    }
    .feedback-btn[aria-pressed='true'] {
      border-color: var(--mm-component-accent);
      color: var(--mm-component-accent);
    }
    .feedback-btn:disabled { opacity: 0.65; cursor: wait; }
    .actions { display: flex; }
  `,
})
export class DiscoverCard {
  readonly item = input.required<DiscoverCardItem>();
  readonly showFeedback = input(false);
  readonly syncFailed = input(false);
  readonly busy = input(false);
  readonly feedback = output<DiscoverFeedback>();
  readonly request = output<void>();

  readonly feedbackOptions = FEEDBACK_OPTIONS;

  meta(): string {
    return formatDiscoverMeta(this.item());
  }

  art(): string {
    return posterArtFor(this.item());
  }

  requestAction() {
    return resolveRequestAction(this.item(), { syncFailed: this.syncFailed() });
  }
}
