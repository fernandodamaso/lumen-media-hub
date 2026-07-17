import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type MmSkeletonVariant = 'text' | 'rect' | 'circle';

@Component({
  selector: 'mm-skeleton',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span
    class="mm-skeleton"
    [class.mm-skeleton--text]="variant() === 'text'"
    [class.mm-skeleton--rect]="variant() === 'rect'"
    [class.mm-skeleton--circle]="variant() === 'circle'"
    [style.width]="width()"
    [style.height]="height()"
    aria-hidden="true"
  ></span>`,
  styles: `
    :host { display: inline-block; }
    .mm-skeleton {
      display: inline-block;
      background: var(--mm-component-muted-bg);
      border-radius: var(--mm-radius-sm);
    }
    .mm-skeleton--text {
      width: 100%;
      height: 1em;
      border-radius: calc(1em / 2);
    }
    .mm-skeleton--circle {
      border-radius: 50%;
      aspect-ratio: 1 / 1;
    }
    .mm-skeleton--rect {
      width: 100%;
      height: 100%;
    }
    @media (prefers-reduced-motion: no-preference) {
      .mm-skeleton {
        animation: mm-skeleton-pulse 2s ease-in-out infinite;
      }
    }
    @keyframes mm-skeleton-pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.45; }
    }
  `,
})
export class MmSkeleton {
  readonly variant = input<MmSkeletonVariant>('text');
  readonly width = input<string | undefined>(undefined);
  readonly height = input<string | undefined>(undefined);
}
