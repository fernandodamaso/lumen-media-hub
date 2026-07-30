import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type ServiceRowStatus = 'healthy' | 'degraded' | 'down' | 'unknown';

@Component({
  selector: 'mm-service-row',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="svc-row">
      <span class="svc-ico" aria-hidden="true">{{ initial() }}</span>
      <div class="svc-copy">
        <div class="svc-name">{{ name() }}</div>
        <div class="svc-sub">{{ detail() }}</div>
      </div>
      <span class="svc-status" [class]="'svc-status--' + status()">
        <span class="dot" aria-hidden="true"></span>{{ statusLabel() }}
      </span>
    </div>
  `,
  styleUrl: './service-row.scss',
})
export class MmServiceRow {
  readonly name = input.required<string>();
  readonly detail = input('');
  readonly status = input<ServiceRowStatus>('unknown');
  readonly statusLabel = input('Unknown');
  readonly initial = input('?');
}
