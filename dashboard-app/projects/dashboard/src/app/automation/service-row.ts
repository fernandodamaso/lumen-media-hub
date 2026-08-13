import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink, UrlTree } from '@angular/router';

export type ServiceRowStatus = 'healthy' | 'degraded' | 'down' | 'unknown';

@Component({
  selector: 'mm-service-row',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="svc-row">
      <span class="svc-ico" aria-hidden="true">
        @if (icon(); as src) {
          <img class="svc-ico-img" [src]="src" alt="" />
        } @else {
          {{ initial() }}
        }
      </span>
      <div class="svc-copy">
        @if (nameHref(); as href) {
          <a
            class="svc-name svc-name--link"
            [href]="href"
            target="_blank"
            rel="noreferrer"
            [attr.aria-label]="'Open ' + name()"
          >{{ name() }}</a>
        } @else {
          <div class="svc-name">{{ name() }}</div>
        }
        <div class="svc-sub">{{ detail() }}</div>
      </div>
      @if (statusLink(); as link) {
        <a
          [class]="'svc-status svc-status--link svc-status--' + status()"
          [routerLink]="link"
          [attr.aria-label]="'View ' + name() + ' live health report'"
        >
          <span class="dot" aria-hidden="true"></span>{{ statusLabel() }}
        </a>
      } @else {
        <span class="svc-status" [class]="'svc-status--' + status()">
          <span class="dot" aria-hidden="true"></span>{{ statusLabel() }}
        </span>
      }
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
  readonly icon = input<string | null>(null);
  readonly nameHref = input<string | null>(null);
  readonly statusLink = input<UrlTree | null>(null);
}
