import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import {
  LucideAlertCircle,
  LucideCircleCheck,
  LucideInfo,
  LucideTriangleAlert,
} from '@lucide/angular';

@Component({
  selector: 'mm-status',
  imports: [LucideCircleCheck, LucideInfo, LucideAlertCircle, LucideTriangleAlert],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span [attr.role]="announce() ? 'status' : null" [class]="'mm-status mm-status--' + tone()">
    @if (tone() === 'success') {
      <svg lucideCircleCheck [size]="15" aria-hidden="true"></svg>
    } @else if (tone() === 'danger') {
      <svg lucideAlertCircle [size]="15" aria-hidden="true"></svg>
    } @else if (tone() === 'warning') {
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
    .mm-status--success { color: var(--mm-component-success); }
    .mm-status--warning { color: var(--mm-component-warning); }
    .mm-status--danger { color: var(--mm-component-danger); }
    .mm-status--info { color: var(--mm-component-info); }
    .mm-status--premiere { color: var(--mm-component-premiere); }
  `,
})
export class MmStatus {
  readonly tone = input<'success' | 'warning' | 'danger' | 'info' | 'premiere'>('info');
  /** When true, exposes a live region for genuinely dynamic status changes. */
  readonly announce = input(false);
}
