import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

@Component({
  selector: 'mm-checkbox',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<label class="mm-checkbox" [class.mm-checkbox--disabled]="disabled()">
    <input type="checkbox" [checked]="checked()" [disabled]="disabled()" (change)="checked.set($any($event.target).checked)" />
    <span class="mm-checkbox__box" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <polyline points="20 6 9 17 4 12"></polyline>
      </svg>
    </span>
    <span class="mm-checkbox__label"><ng-content /></span>
  </label>`,
  styleUrl: './checkbox.scss',
})
export class MmCheckbox {
  readonly checked = model(false);
  readonly disabled = input(false);
}
