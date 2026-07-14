import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MmButton, MmStateCard, MmStatus } from 'media-ui';
import {
  AutomationProblem,
  AutomationProblemSeverity,
  AutomationService,
  AutomationServiceStatus,
} from '../downloads/media-stack-api';
import { AutomationFacade } from './automation.facade';
import {
  AUTOMATION_PROBLEM_SEVERITY_VIEW,
  AUTOMATION_SERVICE_STATUS_VIEW,
  AutomationStatusView,
  formatGeneratedAt,
} from './automation-format';

const SEVERITY_RANK: Record<AutomationProblemSeverity, number> = {
  actionable: 0,
  warning: 1,
  info: 2,
};

const SERVICE_STATUS_RANK: Record<AutomationServiceStatus, number> = {
  down: 0,
  degraded: 1,
  unknown: 2,
  healthy: 3,
};

@Component({
  standalone: true,
  selector: 'mm-automation-board',
  imports: [MmButton, MmStateCard, MmStatus],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="automation" aria-labelledby="automation-heading">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Operations</p>
          <h2 id="automation-heading">Automation</h2>
          <p class="section-copy">Service health, upcoming work, and open problems at a glance.</p>
        </div>
        @if (facade.summary(); as summary) {
          <span class="generated-at">{{ formatGeneratedAt(summary.generatedAt) }}</span>
        }
      </div>

      @if (facade.status() === 'loading') {
        <mm-state-card kind="loading" title="Loading automation" message="Checking automations…" />
      } @else if (facade.status() === 'error') {
        <mm-state-card kind="error" title="Automation unavailable" [message]="facade.error()" tone="danger">
          <mm-button label="Try again" (click)="retry()" />
        </mm-state-card>
      } @else if (facade.status() === 'empty') {
        <mm-state-card kind="empty" title="No automation data" message="No services, previews, or problems have been reported yet." />
      } @else {
        @if (facade.status() === 'partial') {
          <p class="partial-banner" role="status" aria-live="polite">
            <mm-status tone="warning">{{ partialMessage() }}</mm-status>
          </p>
        }

        @if (facade.summary(); as summary) {
          <div class="tile-grid">
            <article class="tile" [attr.aria-label]="'Services (' + summary.services.length + ')'">
              <h3>Services</h3>
              @if (summary.availability.services === 'unavailable') {
                <p class="tile-empty">Service status unavailable.</p>
              } @else if (summary.services.length === 0) {
                <p class="tile-empty">No services reported.</p>
              } @else {
                <ul class="tile-list" aria-live="polite">
                  @for (service of sortedServices(); track service.id || $index) {
                    <li class="tile-row">
                      <span class="tile-title" [attr.title]="service.name">{{ service.name }}</span>
                      @if (service.detail) {
                        <span class="tile-detail">{{ service.detail }}</span>
                      }
                      <mm-status [tone]="serviceStatusView(service.status).tone">{{ serviceStatusView(service.status).label }}</mm-status>
                    </li>
                  }
                </ul>
              }
            </article>

            <article class="tile" [attr.aria-label]="'Preview (' + summary.preview.length + ')'">
              <h3>Up next</h3>
              @if (summary.availability.preview === 'unavailable') {
                <p class="tile-empty">Preview unavailable.</p>
              } @else if (summary.preview.length === 0) {
                <p class="tile-empty">Nothing upcoming.</p>
              } @else {
                <ul class="tile-list" aria-live="polite">
                  @for (item of summary.preview; track item.id || $index) {
                    <li class="tile-row preview-row">
                      <span class="tile-title" [attr.title]="item.title">{{ item.title }}</span>
                      <span class="tile-detail">{{ item.when }}</span>
                      @if (item.kind) {
                        <mm-status tone="info">{{ item.kind }}</mm-status>
                      }
                    </li>
                  }
                </ul>
              }
            </article>

            <article class="tile" [attr.aria-label]="'Problems (' + summary.problems.length + ')'">
              <h3>Problems</h3>
              @if (summary.availability.problems === 'unavailable') {
                <p class="tile-empty">Problem list unavailable.</p>
              } @else if (summary.problems.length === 0) {
                <p class="tile-empty">No open problems.</p>
              } @else {
                <ul class="tile-list" aria-live="polite">
                  @for (problem of sortedProblems(); track problem.id || $index) {
                    <li class="tile-row">
                      <span class="tile-title" [attr.title]="problem.summary">{{ problem.summary }}</span>
                      @if (problem.serviceId) {
                        <span class="tile-detail">{{ problem.serviceId }}</span>
                      }
                      <mm-status [tone]="problemSeverityView(problem.severity).tone">{{ problemSeverityView(problem.severity).label }}</mm-status>
                    </li>
                  }
                </ul>
              }
            </article>
          </div>
        }
      }
    </section>
  `,
  styles: `
    :host { display: block; }
    .automation { margin-top: 0; }
    .section-heading { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 18px; }
    h2 { margin: 0; color: var(--mm-component-text-primary); font-size: 24px; }
    .section-copy { margin-top: 6px; color: var(--mm-component-text-secondary); font-size: 14px; }
    .generated-at { color: var(--mm-component-text-muted); font-size: 13px; }
    .partial-banner { margin: 0 0 14px; }
    .tile-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .tile { display: grid; gap: 12px; padding: 18px; border: 1px solid var(--mm-component-border); border-radius: var(--mm-radius-md); background: var(--mm-component-card-bg); }
    .tile h3 { margin: 0; color: var(--mm-component-text-primary); font-size: 16px; }
    .tile-list { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
    .tile-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 12px; border: 1px solid var(--mm-component-border); border-radius: var(--mm-radius-md); background: var(--mm-component-surface); }
    .preview-row { grid-template-columns: minmax(0, 1fr) auto auto; }
    .tile-title { color: var(--mm-component-text-primary); font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .tile-detail { color: var(--mm-component-text-muted); font-size: 12px; }
    .tile-empty { margin: 0; color: var(--mm-component-text-muted); font-size: 14px; }
    @container (max-width: 520px) {
      .tile-grid { grid-template-columns: 1fr; }
      .section-heading { align-items: start; flex-direction: column; }
      .preview-row { grid-template-columns: minmax(0, 1fr); }
      .tile-row { grid-template-columns: minmax(0, 1fr); }
    }
    @media (max-width: 950px) {
      .tile-grid { grid-template-columns: 1fr; }
      .section-heading { align-items: start; flex-direction: column; }
    }
  `,
})
export class AutomationBoard {
  readonly facade = inject(AutomationFacade);
  readonly formatGeneratedAt = formatGeneratedAt;
  readonly sortedServices = computed(() => this.sortServices(this.facade.summary()?.services ?? []));
  readonly sortedProblems = computed(() => this.sortProblems(this.facade.summary()?.problems ?? []));
  readonly partialMessage = computed(() => {
    const summary = this.facade.summary();
    if (!summary) return 'Some automation data is unavailable.';
    const names = Object.entries(summary.availability)
      .filter(([, value]) => value === 'unavailable')
      .map(([key]) => key);
    if (names.length === 0) return 'Some automation data is unavailable.';
    return `${this.joinNames(names)} unavailable.`;
  });

  constructor() {
    this.facade.startPolling();
  }

  serviceStatusView(status: AutomationServiceStatus): AutomationStatusView {
    return AUTOMATION_SERVICE_STATUS_VIEW[status];
  }

  problemSeverityView(severity: AutomationProblemSeverity): AutomationStatusView {
    return AUTOMATION_PROBLEM_SEVERITY_VIEW[severity];
  }

  retry(): void {
    void this.facade.refresh();
  }

  private sortServices(services: AutomationService[]): AutomationService[] {
    return [...services].sort(
      (left, right) =>
        SERVICE_STATUS_RANK[left.status] - SERVICE_STATUS_RANK[right.status] ||
        left.name.localeCompare(right.name),
    );
  }

  private sortProblems(problems: AutomationProblem[]): AutomationProblem[] {
    return [...problems].sort(
      (left, right) => SEVERITY_RANK[left.severity] - SEVERITY_RANK[right.severity] || left.summary.localeCompare(right.summary),
    );
  }

  private joinNames(names: string[]): string {
    const capitalized = names.map((name) => name.charAt(0).toUpperCase() + name.slice(1));
    if (capitalized.length === 1) return `${capitalized[0]} is`;
    const head = capitalized.slice(0, -1).join(', ');
    const tail = capitalized[capitalized.length - 1];
    return `${head} and ${tail} are`;
  }
}
