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
    :host {
      display: inline-block;
      max-width: 100%;
      min-width: 0;
      vertical-align: top;
    }
    .mm-skeleton {
      position: relative;
      overflow: hidden;
      display: block;
      max-width: 100%;
      box-sizing: border-box;
      background-color: var(--mm-component-raised-bg);
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
      .mm-skeleton::after {
        content: '';
        position: absolute;
        inset: 0;
        border-radius: inherit;
        background-image: linear-gradient(
          100deg,
          transparent 35%,
          color-mix(in srgb, var(--mm-component-text-primary) 18%, transparent) 50%,
          transparent 65%
        );
        background-size: 220% 100%;
        animation: mm-skeleton-shimmer 1.6s linear infinite;
        will-change: background-position;
      }
    }
    @keyframes mm-skeleton-shimmer {
      from { background-position: 160% 0; }
      to   { background-position: -60% 0; }
    }
  `,
})
export class MmSkeleton {
  readonly variant = input<MmSkeletonVariant>('text');
  readonly width = input<string | undefined>(undefined);
  readonly height = input<string | undefined>(undefined);
}
