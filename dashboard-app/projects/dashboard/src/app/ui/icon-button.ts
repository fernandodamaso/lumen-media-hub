import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { LucideLoaderCircle } from '@lucide/angular';

@Component({
  selector: 'mm-icon-button',
  imports: [LucideLoaderCircle],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '[class.mm-icon-button-host--disabled]': 'disabled() || busy()',
  },
  template: `<button
    type="button"
    class="mm-icon-button"
    [class.mm-icon-button--sm]="size() === 'sm'"
    [class.mm-icon-button--md]="size() === 'md'"
    [class.mm-icon-button--rounded]="shape() === 'rounded'"
    [class.mm-icon-button--circle]="shape() === 'circle'"
    [class.mm-icon-button--pressed]="pressed()"
    [disabled]="disabled() || busy()"
    [attr.aria-label]="label()"
    [attr.aria-pressed]="toggle() ? pressed() : null"
    [attr.aria-expanded]="expanded() ?? null"
    [attr.aria-controls]="ariaControls() ?? null"
    [attr.aria-busy]="busy() || null"
    [attr.title]="label()"
  >
    @if (busy()) {
      <svg class="mm-icon-button__spinner" lucideLoaderCircle [size]="14" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else {
      <ng-content />
    }
  </button>`,
  styleUrl: './icon-button.scss',
})
export class MmIconButton {
  readonly label = input.required<string>();
  readonly disabled = input(false);
  readonly busy = input(false);
  readonly pressed = input(false);
  readonly expanded = input<boolean | undefined>();
  readonly ariaControls = input<string | undefined>();
  /** When true, exposes `aria-pressed` as true/false for toggle buttons. */
  readonly toggle = input(false);
  readonly size = input<'sm' | 'md'>('md');
  readonly shape = input<'rounded' | 'circle'>('rounded');
}
