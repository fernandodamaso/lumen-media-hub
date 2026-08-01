import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import { LucidePlay } from '@lucide/angular';

export type MmPosterTagTone = 'accent' | 'success';
export type MmPosterCaptionPlacement = 'overlay' | 'below';

@Component({
  selector: 'mm-poster',
  imports: [LucidePlay],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './poster.html',
  styleUrl: './poster.scss',
})
export class MmPoster {
  readonly title = input('Moonrise');
  readonly meta = input('2026 · Drama');
  readonly rating = input<number | null>(null);
  readonly imageUrl = input<string | null | undefined>(null);
  readonly framed = input(true);
  readonly episode = input<string | null>(null);
  readonly tag = input<string | null>(null);
  readonly tagTone = input<MmPosterTagTone>('accent');
  readonly progress = input<number | null>(null);
  readonly href = input<string | null>(null);
  readonly linkLabel = input<string | null>(null);
  readonly captionPlacement = input<MmPosterCaptionPlacement>('overlay');
  readonly showPlayCue = input(false);
  readonly art = input(
    'linear-gradient(145deg, color-mix(in srgb, var(--mm-component-accent) 28%, var(--mm-component-card-bg)), var(--mm-component-card-bg) 72%)',
  );

  readonly resolvedLinkLabel = computed(() => this.linkLabel() ?? `Open ${this.title()}`);

  private readonly imageErrorKey = signal<string | null>(null);

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
