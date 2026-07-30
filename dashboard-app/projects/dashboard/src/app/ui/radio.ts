import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

@Component({
  selector: 'mm-radio',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<label class="mm-radio" [class.mm-radio--disabled]="disabled()">
    <input type="radio" [name]="name()" [value]="value()" [checked]="checked()" [disabled]="disabled()" (change)="valueSelect.emit(value())" />
    <span class="mm-radio__dot" aria-hidden="true"></span>
    <span class="mm-radio__label"><ng-content /></span>
  </label>`,
  styleUrl: './radio.scss',
})
export class MmRadio {
  readonly name = input.required<string>();
  readonly value = input.required<string>();
  readonly checked = input(false);
  readonly disabled = input(false);
  readonly valueSelect = output<string>();
}
