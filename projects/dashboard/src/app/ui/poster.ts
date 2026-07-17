import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'mm-poster',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './poster.html',
  styleUrl: './poster.scss',
})
export class MmPoster {
  readonly title = input('Moonrise');
  readonly meta = input('2026 · Drama');
  readonly rating = input<number | null>(null);
  readonly art = input(
    'linear-gradient(145deg, color-mix(in srgb, var(--mm-component-accent) 28%, var(--mm-component-card-bg)), var(--mm-component-card-bg) 72%)',
  );
}
