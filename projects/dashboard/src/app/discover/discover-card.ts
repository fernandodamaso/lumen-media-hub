import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { LucideEye, LucideSkipForward, LucideThumbsDown, LucideThumbsUp } from '@lucide/angular';
import { MmButton, MmPoster, MmStatus } from 'media-ui';
import { DiscoverFeedback } from '../downloads/media-stack-api';
import {
  DiscoverCardItem,
  formatDiscoverMeta,
  posterArtFor,
  resolveRequestAction,
} from './discover-format';

const FEEDBACK_OPTIONS: {
  value: DiscoverFeedback;
  label: string;
  icon: 'thumbsUp' | 'thumbsDown' | 'eye' | 'skipForward';
}[] = [
  { value: 'liked', label: 'Liked', icon: 'thumbsUp' },
  { value: 'disliked', label: 'Disliked', icon: 'thumbsDown' },
  { value: 'watched', label: 'Watched', icon: 'eye' },
  { value: 'skipped', label: 'Skipped', icon: 'skipForward' },
];

@Component({
  selector: 'mm-discover-card',
  imports: [MmButton, MmPoster, MmStatus, LucideThumbsUp, LucideThumbsDown, LucideEye, LucideSkipForward],
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
                [attr.aria-label]="option.label"
                [attr.aria-pressed]="item().feedback === option.value"
                [disabled]="busy()"
                (click)="feedback.emit(option.value)"
              >
                @switch (option.icon) {
                  @case ('thumbsUp') {
                    <svg lucideThumbsUp [size]="16" [strokeWidth]="2.2" aria-hidden="true"></svg>
                  }
                  @case ('thumbsDown') {
                    <svg lucideThumbsDown [size]="16" [strokeWidth]="2.2" aria-hidden="true"></svg>
                  }
                  @case ('eye') {
                    <svg lucideEye [size]="16" [strokeWidth]="2.2" aria-hidden="true"></svg>
                  }
                  @case ('skipForward') {
                    <svg lucideSkipForward [size]="16" [strokeWidth]="2.2" aria-hidden="true"></svg>
                  }
                }
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
              (click)="onRequest()"
            />
          </span>
        </div>
      </div>
    </article>
  `,
  styles: `
    :host {
      display: block;
    }
    .discover-card {
      display: grid;
      gap: 12px;
      align-content: start;
    }
    .body {
      display: grid;
      gap: 10px;
    }
    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      min-height: 28px;
    }
    .reason {
      margin: 0;
      color: var(--mm-component-text-secondary);
      font-size: var(--mm-text-sm);
      line-height: 1.45;
      min-height: 2.9em;
    }
    .feedback {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .feedback-btn {
      display: inline-grid;
      place-items: center;
      width: 34px;
      height: 34px;
      padding: 0;
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-sm);
      background: var(--mm-component-control-bg);
      color: var(--mm-component-text-primary);
      cursor: pointer;
      transition:
        background var(--mm-transition-fast),
        border-color var(--mm-transition-fast),
        color var(--mm-transition-fast);
    }
    .feedback-btn:hover:not(:disabled) {
      background: var(--mm-component-muted-bg);
    }
    .feedback-btn:focus-visible {
      outline: 3px solid var(--mm-component-focus-ring);
      outline-offset: 2px;
    }
    .feedback-btn[aria-pressed='true'] {
      background: color-mix(in srgb, var(--mm-component-accent) 12%, transparent);
      border-color: var(--mm-component-accent);
      color: var(--mm-component-accent);
    }
    .feedback-btn:disabled {
      opacity: 0.65;
      cursor: wait;
    }
    .actions {
      display: flex;
    }
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

  readonly meta = computed(() => formatDiscoverMeta(this.item()));
  readonly art = computed(() => posterArtFor(this.item()));
  readonly requestAction = computed(() =>
    resolveRequestAction(this.item(), { syncFailed: this.syncFailed() }),
  );

  onRequest(): void {
    if (this.requestAction().disabled || this.busy()) return;
    this.request.emit();
  }
}
