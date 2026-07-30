import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

@Component({
  selector: 'mm-checkbox',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<label class="mm-checkbox" [class.mm-checkbox--disabled]="disabled()">
    <input type="checkbox" [checked]="checked()" [disabled]="disabled()" (change)="checkedChange.emit($any($event.target).checked)" />
    <span class="mm-checkbox__box" aria-hidden="true"></span>
    <span class="mm-checkbox__label"><ng-content /></span>
  </label>`,
  styleUrl: './checkbox.scss',
})
export class MmCheckbox {
  readonly checked = input(false);
  readonly disabled = input(false);
  readonly checkedChange = output<boolean>();
}
