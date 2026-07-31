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
      gap: 6px;
      border-radius: 999px;
      padding: 5px 13px;
      border: 1px solid var(--mm-status-border, var(--mm-component-border));
      background: var(--mm-status-bg, var(--mm-component-muted-bg));
      color: var(--mm-status-text, var(--mm-component-text-secondary));
      font: 700 10.5px/1 var(--mm-font-body);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .mm-status__dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: currentColor;
    }
    .mm-status--success,
    .mm-status--green {
      --mm-status-text: var(--mm-component-success);
      --mm-status-border: color-mix(in srgb, var(--mm-component-success) 35%, transparent);
      --mm-status-bg: color-mix(in srgb, var(--mm-component-success) 10%, transparent);
    }
    .mm-status--warning,
    .mm-status--amber {
      --mm-status-text: var(--mm-component-warning);
      --mm-status-border: color-mix(in srgb, var(--mm-component-warning) 35%, transparent);
      --mm-status-bg: color-mix(in srgb, var(--mm-component-warning) 10%, transparent);
    }
    .mm-status--danger,
    .mm-status--red {
      --mm-status-text: var(--mm-component-danger);
      --mm-status-border: color-mix(in srgb, var(--mm-component-danger) 35%, transparent);
      --mm-status-bg: color-mix(in srgb, var(--mm-component-danger) 10%, transparent);
    }
    .mm-status--info {
      --mm-status-text: var(--mm-component-info);
      --mm-status-border: color-mix(in srgb, var(--mm-component-info) 35%, transparent);
      --mm-status-bg: color-mix(in srgb, var(--mm-component-info) 10%, transparent);
    }
    .mm-status--premiere,
    .mm-status--violet {
      --mm-status-text: var(--mm-component-premiere);
      --mm-status-border: color-mix(in srgb, var(--mm-component-premiere) 35%, transparent);
      --mm-status-bg: color-mix(in srgb, var(--mm-component-premiere) 10%, transparent);
    }
    .mm-status--gold {
      --mm-status-text: var(--mm-semantic-accent);
      --mm-status-border: color-mix(in srgb, var(--mm-semantic-accent) 35%, transparent);
      --mm-status-bg: color-mix(in srgb, var(--mm-semantic-accent) 10%, transparent);
    }
    .mm-status--neutral {
      --mm-status-text: var(--mm-component-text-secondary);
      --mm-status-border: var(--mm-component-border);
      --mm-status-bg: var(--mm-component-muted-bg);
    }
  `,
})
export class MmStatus {
  readonly tone = input<MmStatusTone>('info');
  /** When true, exposes a live region for genuinely dynamic status changes. */
  readonly announce = input(false);
  /** Badge-style dot instead of icon (mock badge merge). */
  readonly dot = input(false);
}
