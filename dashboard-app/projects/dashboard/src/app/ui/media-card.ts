import { ChangeDetectionStrategy, Component, computed, effect, input, signal } from '@angular/core';
import { LucidePlay } from '@lucide/angular';
import { MmProgress } from './progress';

export type MmMediaCardLayout = 'portrait' | 'landscape';
export type MmMediaCardTagTone = 'accent' | 'success';
export type MmMediaCardCaptionPlacement = 'overlay' | 'below';

@Component({
  selector: 'mm-media-card',
  imports: [MmProgress, LucidePlay],
  host: {
    '[class.mm-media-card--landscape]': "layout() === 'landscape'",
  },
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './media-card.html',
  styleUrl: './media-card.scss',
})
export class MmMediaCard {
  readonly layout = input<MmMediaCardLayout>('portrait');
  readonly title = input('');
  readonly subtitle = input('');
  readonly rating = input<number | null>(null);
  readonly imageUrl = input<string | null | undefined>(null);
  readonly framed = input(true);
  readonly episode = input<string | null>(null);
  readonly tag = input<string | null>(null);
  readonly tagTone = input<MmMediaCardTagTone>('accent');
  readonly progress = input<number | null>(null);
  readonly href = input<string | null>(null);
  readonly linkLabel = input<string | null>(null);
  readonly captionPlacement = input<MmMediaCardCaptionPlacement>('overlay');
  readonly showPlayCue = input(false);
  readonly retryToken = input<unknown>(null);
  readonly art = input(
    'linear-gradient(145deg, color-mix(in srgb, var(--mm-component-accent) 28%, var(--mm-component-card-bg)), var(--mm-component-card-bg) 72%)',
  );

  readonly resolvedLinkLabel = computed(() => this.linkLabel() ?? `Open ${this.title()}`);

  private readonly imageErrorKey = signal<string | null>(null);

  constructor() {
    effect(() => {
      this.retryToken();
      this.imageErrorKey.set(null);
    });
  }

  private readonly imageKey = computed(() => this.imageUrl() ?? '');

  readonly showNetworkImage = computed(() => {
    const url = this.imageUrl();
    if (!url) return false;
    return this.imageErrorKey() !== this.imageKey();
  });

  onImageError(): void {
    this.imageErrorKey.set(this.imageKey());
  }
}
