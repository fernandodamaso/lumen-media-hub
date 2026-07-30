import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { LucideLoaderCircle, LucidePause, LucidePlay, LucidePlus, LucideRefreshCw, LucideSquareArrowOutUpRight } from '@lucide/angular';

@Component({
  selector: 'mm-button',
  imports: [LucideLoaderCircle, LucidePause, LucidePlay, LucidePlus, LucideRefreshCw, LucideSquareArrowOutUpRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button
    [type]="type()"
    [disabled]="disabled() || busy()"
    [attr.aria-busy]="busy() || null"
    [class]="'mm-button mm-button--' + variant()"
  >
    @if (busy()) {
      <svg lucideLoaderCircle [size]="16" [strokeWidth]="2.2" aria-hidden="true"></svg>
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
    }
    {{ label() }}
  </button>`,
  styleUrl: './button.scss',
})
export class MmButton {
  readonly label = input('Continue');
  readonly variant = input<'primary' | 'quiet' | 'success' | 'warning' | 'danger' | 'gold' | 'ghost'>('primary');
  readonly icon = input<'pause' | 'play' | 'plus' | 'refresh' | 'external-link' | ''>('');
  readonly disabled = input(false);
  readonly busy = input(false);
  readonly type = input<'button' | 'submit'>('button');
}
