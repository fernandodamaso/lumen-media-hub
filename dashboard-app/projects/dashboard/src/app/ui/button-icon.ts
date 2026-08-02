import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import {
  LucideInfo,
  LucideLoaderCircle,
  LucidePause,
  LucidePlay,
  LucidePlus,
  LucideRefreshCw,
  LucideSquareArrowOutUpRight,
} from '@lucide/angular';
import { MmButtonIconName } from './button-shared';

@Component({
  selector: 'mm-button-icon',
  imports: [
    LucideInfo,
    LucideLoaderCircle,
    LucidePause,
    LucidePlay,
    LucidePlus,
    LucideRefreshCw,
    LucideSquareArrowOutUpRight,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (busy()) {
      <svg class="mm-button__spinner" lucideLoaderCircle [size]="16" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'pause') {
      <svg lucidePause [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'play') {
      <svg lucidePlay [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'plus') {
      <svg lucidePlus [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'refresh') {
      <svg lucideRefreshCw [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'external-link') {
      <svg lucideSquareArrowOutUpRight [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'info') {
      <svg lucideInfo [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    }
  `,
  styleUrl: './button.scss',
})
export class MmButtonIcon {
  readonly icon = input<MmButtonIconName>('');
  readonly busy = input(false);
}
