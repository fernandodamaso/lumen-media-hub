import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { MmButtonIcon } from './button-icon';
import { MmButtonIconName, MmButtonSize, MmButtonVariant, mmButtonClasses } from './button-shared';

@Component({
  selector: 'mm-button',
  imports: [MmButtonIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button
    [type]="type()"
    [disabled]="disabled() || busy()"
    [attr.aria-busy]="busy() || null"
    [class]="classes()"
  >
    <mm-button-icon [icon]="icon()" [busy]="busy()" />
    {{ label() }}
  </button>`,
  styleUrl: './button.scss',
})
export class MmButton {
  readonly label = input('Continue');
  readonly variant = input<MmButtonVariant>('primary');
  readonly icon = input<MmButtonIconName>('');
  readonly disabled = input(false);
  readonly busy = input(false);
  readonly size = input<MmButtonSize>('md');
  readonly type = input<'button' | 'submit'>('button');
  readonly solid = input(false);
  /** When false, hover keeps the button on the same baseline (matches icon controls). */
  readonly liftOnHover = input(true);

  classes(): string {
    return mmButtonClasses({
      variant: this.variant(),
      size: this.size(),
      solid: this.solid(),
      liftOnHover: this.liftOnHover(),
    });
  }
}
