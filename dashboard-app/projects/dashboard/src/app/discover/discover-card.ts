import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { LucideEye, LucideSkipForward, LucideThumbsDown, LucideThumbsUp } from '@lucide/angular';
import { MmButton, MmIconButton, MmMediaCard, MmPosterActionOverlay, MmStatus } from '@app/ui';
import { DiscoverFeedback } from './discover.models';
import {
  DiscoverCardItem,
  discoverPosterFallback,
  formatDiscoverMeta,
  isDiscoverFeedbackPressed,
  isWatchedFeedbackDisabled,
  resolveRequestAction,
  traktHistorySyncLabel,
  traktHistorySyncTone,
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
  imports: [MmButton, MmIconButton, MmMediaCard, MmPosterActionOverlay, MmStatus, LucideThumbsUp, LucideThumbsDown, LucideEye, LucideSkipForward],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './discover-card.html',
  styleUrl: './discover-card.scss',
})
export class DiscoverCard {
  readonly item = input.required<DiscoverCardItem>();
  readonly showFeedback = input(false);
  readonly showSummary = input(true);
  readonly syncFailed = input(false);
  readonly busy = input(false);
  readonly feedback = output<DiscoverFeedback>();
  readonly request = output();

  readonly feedbackOptions = FEEDBACK_OPTIONS;

  readonly meta = computed(() => formatDiscoverMeta(this.item()));
  readonly fallbackArt = computed(() => discoverPosterFallback(this.item().title));
  readonly requestAction = computed(() =>
    resolveRequestAction(this.item(), { syncFailed: this.syncFailed() }),
  );

  readonly summaryText = computed(() => this.item().reason ?? this.item().overview ?? '');

  readonly traktSyncLabel = computed(() => traktHistorySyncLabel(this.item().traktHistorySync?.status));

  readonly traktSyncTone = computed(() => traktHistorySyncTone(this.item().traktHistorySync?.status));

  isFeedbackDisabled(option: DiscoverFeedback): boolean {
    if (this.busy()) return true;
    return option === 'watched' && isWatchedFeedbackDisabled(this.item());
  }

  isFeedbackPressed(option: DiscoverFeedback): boolean {
    return isDiscoverFeedbackPressed(this.item().feedback, option, this.item().traktHistorySync);
  }

  onRequest(): void {
    if (this.requestAction().disabled || this.busy()) return;
    this.request.emit();
  }
}
