import { DecimalPipe, NgTemplateOutlet } from '@angular/common';
import { afterNextRender, ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { map } from 'rxjs';
import { MmButton, MmDialog, MmStateCard, MmStatus } from '@app/ui';
import {
  AUTOMATION_PROBLEM_SEVERITY_VIEW,
  AUTOMATION_SERVICE_STATUS_VIEW,
} from '../automation/automation-format';
import {
  AutomationProblemSeverity,
  AutomationService,
  AutomationServiceStatus,
} from '../automation/automation.models';
import { serviceIconPath } from '../automation/service-catalog';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { MmServiceRow } from '../automation/service-row';
import { buildServiceHealthReportView, cronStatusView, formatRunTimestamp } from './reports-format';
import { ReportsFacade } from './reports.facade';
import type { CronHistoricalRun } from './reports.models';

@Component({
  selector: 'mm-reports-page',
  imports: [DecimalPipe, NgTemplateOutlet, MmButton, MmDialog, MmStateCard, MmStatus, MmServiceRow],
  providers: [ReportsFacade],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './reports-page.html',
  styleUrl: './reports-page.scss',
})
export class ReportsPage {
  readonly facade = inject(ReportsFacade);
  readonly health = inject(ServiceHealthFacade);
  private readonly route = inject(ActivatedRoute);
  readonly formatRunTimestamp = formatRunTimestamp;
  readonly statusView = cronStatusView;

  private readonly expandedIds = signal(new Set<string>());
  readonly expanded = this.expandedIds.asReadonly();

  readonly selectedServiceId = toSignal(
    this.route.queryParamMap.pipe(map((params) => params.get('service'))),
    { initialValue: null as string | null },
  );

  private readonly routeFragment = toSignal(this.route.fragment, { initialValue: null as string | null });

  readonly healthView = computed(() =>
    buildServiceHealthReportView(
      this.health.services(),
      this.health.problems(),
      this.selectedServiceId(),
    ),
  );

  readonly refreshing = computed(() => this.facade.refreshing() || this.health.refreshing());

  readonly actionableRuns = computed(() => this.facade.currentRuns().filter((run) => run.triage === 'actionable'));
  readonly healthyRuns = computed(() => this.facade.currentRuns().filter((run) => run.triage === 'quiet'));
  readonly historyRuns = this.facade.historyRuns;
  readonly confirmCleanup = signal(false);
  readonly queueHygiene = this.health.queueHygiene;

  constructor() {
    void this.facade.load();
    afterNextRender(() => {
      this.scrollToServiceHealthIfNeeded();
    });
    effect(() => {
      this.routeFragment();
      this.selectedServiceId();
      this.health.status();
      queueMicrotask(() => {
        this.scrollToServiceHealthIfNeeded();
      });
    });
  }

  refresh(): void {
    void Promise.all([this.facade.refresh(), this.health.refresh()]);
  }

  previewQueueHygiene(): void {
    void this.health.runQueueHygiene('observe');
  }

  openCleanupConfirmation(): void {
    if (this.canRunCleanup()) this.confirmCleanup.set(true);
  }

  cancelCleanupConfirmation(): void {
    this.confirmCleanup.set(false);
  }

  confirmSafeCleanup(): void {
    this.confirmCleanup.set(false);
    if (this.canRunCleanup()) void this.health.runQueueHygiene('auto');
  }

  canRunCleanup(): boolean {
    const hygiene = this.queueHygiene();
    return hygiene !== null && hygiene.eligibleCount > 0 && !hygiene.circuitOpen && !this.health.queueHygieneRunning();
  }

  onToggle(id: string, event: Event): void {
    const open = (event.target as HTMLDetailsElement).open;
    const next = new Set(this.expandedIds());
    if (open) next.add(id);
    else next.delete(id);
    this.expandedIds.set(next);
  }

  historyBadge(run: CronHistoricalRun): { label: string; tone: 'success' | 'info' } {
    return run.resolved
      ? { label: 'Resolved', tone: 'success' }
      : { label: 'Historical', tone: 'info' };
  }

  serviceInitial(name: string): string {
    return (name.charAt(0) || '?').toUpperCase();
  }

  serviceIcon(id: string): string | null {
    return serviceIconPath(id);
  }

  serviceStatusLabel(status: AutomationServiceStatus): string {
    return AUTOMATION_SERVICE_STATUS_VIEW[status].label;
  }

  serviceDetail(service: AutomationService): string {
    return service.detail || this.serviceStatusLabel(service.status);
  }

  problemSeverityView(severity: AutomationProblemSeverity) {
    return AUTOMATION_PROBLEM_SEVERITY_VIEW[severity];
  }

  private scrollToServiceHealthIfNeeded(): void {
    if (this.routeFragment() !== 'service-health') return;
    document.getElementById('service-health')?.scrollIntoView({ block: 'start' });
  }
}
