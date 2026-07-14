import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'mm-progress',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div
      class="mm-progress"
      role="progressbar"
      [attr.aria-label]="label()"
      [attr.aria-valuenow]="value()"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <div class="mm-progress__bar" [style.width.%]="value()"></div>
    </div>
    <span class="mm-progress__label">{{ value() }}%</span>`,
  styles: `
    :host {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
    }
    .mm-progress {
      height: 8px;
      overflow: hidden;
      flex: 1;
      border-radius: 999px;
      background: var(--mm-component-border);
    }
    .mm-progress__bar {
      height: 100%;
      border-radius: inherit;
      background: var(--mm-component-accent);
      transition: width var(--mm-transition-normal);
    }
    .mm-progress__label {
      min-width: 38px;
      color: var(--mm-component-text-secondary);
      font-size: var(--mm-text-xs);
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
  `,
})
export class MmProgress {
  readonly value = input(0);
  readonly label = input('Progress');
}
