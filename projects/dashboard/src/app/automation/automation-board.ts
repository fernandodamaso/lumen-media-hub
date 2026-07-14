import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MmButton, MmCard, MmStateCard, MmStatus } from 'media-ui';
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
  imports: [MmButton, MmCard, MmStateCard, MmStatus],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mm-card class="automation" labelledBy="automation-heading">
      <div mm-card-header>
        <div>
          <p class="eyebrow">Operations</p>
          <h2 id="automation-heading">Automation</h2>
          <p class="section-copy">Service health, upcoming work, and open problems at a glance.</p>
        </div>
      </div>
      <div mm-card-header-actions>
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

            <article class="tile" [attr.aria-label]="'Up Next Scheduled Tasks (' + facade.tasks().length + ')'">
              <h3>Up Next Scheduled Tasks</h3>
              @if (facade.tasksUnavailable()) {
                <p class="tile-empty">Scheduled tasks unavailable.</p>
              } @else if (facade.tasks().length === 0) {
                <p class="tile-empty">No scheduled tasks.</p>
              } @else {
                <ul class="tile-list" aria-live="polite">
                  @for (item of facade.tasks(); track item.jobId) {
                    <li class="tile-row preview-row">
                      <span class="tile-title" [attr.title]="item.jobTitle">{{ item.jobTitle }}</span>
                      <span class="tile-detail task-detail">
                        <span class="task-schedule">{{ item.schedule || 'Not scheduled' }}</span>
                        <span aria-hidden="true">·</span>
                        <span class="task-timestamp">{{ item.timestamp ? formatGeneratedAt(item.timestamp) : 'No recent run' }}</span>
                      </span>
                      <mm-status [tone]="item.triage === 'actionable' ? 'warning' : 'success'">{{ item.status }}</mm-status>
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
    </mm-card>
  `,
  styles: `
    :host { display: block; }
    .automation { margin-top: 0; }
    .section-heading { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 18px; }
    h2 { margin: 0; color: var(--mm-component-text-primary); font-size: 24px; }
    .section-copy { margin-top: 6px; color: var(--mm-component-text-secondary); font-size: 14px; }
    .generated-at { color: var(--mm-component-text-muted); font-size: 13px; }
    .partial-banner { margin: 0 0 14px; }
    .tile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
    .tile { display: grid; gap: 12px; padding: 18px; border: 1px solid var(--mm-component-border); border-radius: var(--mm-radius-md); background: var(--mm-component-card-bg); }
    .tile:first-child { grid-column: 1 / -1; }
    .tile h3 { margin: 0; color: var(--mm-component-text-primary); font-size: 16px; }
    .tile-list { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
    .tile-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 12px; border: 1px solid var(--mm-component-border); border-radius: var(--mm-radius-md); background: var(--mm-component-control-bg); }
    .preview-row { align-items: start; }
    .tile-title { min-width: 0; color: var(--mm-component-text-primary); font-size: 14px; font-weight: 600; overflow-wrap: normal; word-break: normal; white-space: normal; }
    .tile-detail { color: var(--mm-component-text-muted); font-size: 12px; }
    .tile-row .tile-detail { grid-column: 1; }
    .task-detail { display: flex; flex-wrap: wrap; gap: 4px; }
    .task-schedule,
    .task-timestamp { white-space: nowrap; }
    .tile-row mm-status { grid-column: 2; grid-row: 1 / span 2; white-space: nowrap; }
    .tile-empty { margin: 0; color: var(--mm-component-text-muted); font-size: 14px; }
    @container (max-width: 520px) {
      .tile-grid { grid-template-columns: 1fr; }
      .tile:first-child { grid-column: auto; }
      .section-heading { align-items: start; flex-direction: column; }
      .tile-row { grid-template-columns: minmax(0, 1fr); }
      .tile-row mm-status { grid-column: 1; grid-row: auto; justify-self: start; }
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
    const names: string[] = [];
    if (this.facade.summaryUnavailable()) names.push('automation summary');
    if (summary?.availability.services === 'unavailable') names.push('services');
    if (summary?.availability.problems === 'unavailable') names.push('problem list');
    if (this.facade.tasksUnavailable()) names.push('scheduled tasks');
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
