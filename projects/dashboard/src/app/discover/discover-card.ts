import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { LucideEye, LucideSkipForward, LucideThumbsDown, LucideThumbsUp } from '@lucide/angular';
import { MmButton, MmPoster, MmStatus } from '@app/ui';
import { DiscoverFeedback } from './discover.models';
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
  templateUrl: './discover-card.html',
  styleUrl: './discover-card.scss',
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
