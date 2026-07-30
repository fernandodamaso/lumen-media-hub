import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import {
  LucideCircleAlert,
  LucideCircleCheck,
  LucideInfo,
  LucideTriangleAlert,
} from '@lucide/angular';

export type MmStatusTone =
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'premiere'
  | 'gold'
  | 'green'
  | 'amber'
  | 'violet'
  | 'red'
  | 'neutral';

@Component({
  selector: 'mm-status',
  imports: [LucideCircleCheck, LucideInfo, LucideCircleAlert, LucideTriangleAlert],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span
    [attr.role]="announce() ? 'status' : null"
    [class]="'mm-status mm-status--' + tone()"
  >
    @if (dot()) {
      <span class="mm-status__dot" aria-hidden="true"></span>
    } @else if (tone() === 'success' || tone() === 'green') {
      <svg lucideCircleCheck [size]="15" aria-hidden="true"></svg>
    } @else if (tone() === 'danger' || tone() === 'red') {
      <svg lucideCircleAlert [size]="15" aria-hidden="true"></svg>
    } @else if (tone() === 'warning' || tone() === 'amber') {
      <svg lucideTriangleAlert [size]="15" aria-hidden="true"></svg>
    } @else {
      <svg lucideInfo [size]="15" aria-hidden="true"></svg>
    }
    <span><ng-content /></span>
  </span>`,
  styles: `
    .mm-status {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      border-radius: 999px;
      padding: 4px 8px;
      background: var(--mm-component-muted-bg);
      color: var(--mm-component-text-secondary);
      font: 700 var(--mm-text-xs)/1 var(--mm-font-body);
    }
    .mm-status__dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: currentColor;
    }
    .mm-status--success, .mm-status--green { color: var(--mm-component-success); }
    .mm-status--warning, .mm-status--amber { color: var(--mm-component-warning); }
    .mm-status--danger, .mm-status--red { color: var(--mm-component-danger); }
    .mm-status--info, .mm-status--neutral { color: var(--mm-component-info); }
    .mm-status--premiere, .mm-status--violet { color: var(--mm-component-premiere); }
    .mm-status--gold { color: var(--mm-semantic-accent); }
  `,
})
export class MmStatus {
  readonly tone = input<MmStatusTone>('info');
  /** When true, exposes a live region for genuinely dynamic status changes. */
  readonly announce = input(false);
  /** Badge-style dot instead of icon (mock badge merge). */
  readonly dot = input(false);
}
