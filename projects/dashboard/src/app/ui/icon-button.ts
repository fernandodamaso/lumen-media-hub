import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { LucideLoaderCircle } from '@lucide/angular';

@Component({
  selector: 'mm-icon-button',
  imports: [LucideLoaderCircle],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button
    type="button"
    class="mm-icon-button"
    [class.mm-icon-button--pressed]="pressed()"
    [disabled]="disabled() || busy()"
    [attr.aria-label]="label()"
    [attr.aria-pressed]="pressed() ? true : null"
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
}
