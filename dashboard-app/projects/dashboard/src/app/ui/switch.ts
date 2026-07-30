import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

@Component({
  selector: 'mm-switch',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<label class="mm-switch" [class.mm-switch--on]="checked()" [class.mm-switch--disabled]="disabled()">
    <input type="checkbox" role="switch" [checked]="checked()" [disabled]="disabled()" (change)="checkedChange.emit($any($event.target).checked)" />
    <span class="mm-switch__track" aria-hidden="true"><span class="mm-switch__thumb"></span></span>
    <span class="mm-switch__label"><ng-content /></span>
  </label>`,
  styleUrl: './switch.scss',
})
export class MmSwitch {
  readonly checked = input(false);
  readonly disabled = input(false);
  readonly checkedChange = output<boolean>();
}
