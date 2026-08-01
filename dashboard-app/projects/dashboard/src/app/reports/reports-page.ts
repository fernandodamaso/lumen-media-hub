import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MmButton, MmStateCard, MmStatus } from '@app/ui';
import { cronStatusView, formatRunTimestamp } from './reports-format';
import { ReportsFacade } from './reports.facade';

@Component({
  selector: 'mm-reports-page',
  imports: [NgTemplateOutlet, MmButton, MmStateCard, MmStatus],
  providers: [ReportsFacade],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './reports-page.html',
  styleUrl: './reports-page.scss',
})
export class ReportsPage {
  readonly facade = inject(ReportsFacade);
  readonly formatRunTimestamp = formatRunTimestamp;
  readonly statusView = cronStatusView;

  private readonly expandedIds = signal(new Set<string>());
  readonly expanded = this.expandedIds.asReadonly();

  readonly actionableRuns = computed(() => this.facade.runs().filter((run) => run.triage === 'actionable'));
  readonly quietRuns = computed(() => this.facade.runs().filter((run) => run.triage === 'quiet'));

  constructor() {
    void this.facade.load();
  }

  refresh(): void {
    void this.facade.refresh();
  }

  onToggle(id: string, event: Event): void {
    const open = (event.target as HTMLDetailsElement).open;
    const next = new Set(this.expandedIds());
    if (open) next.add(id);
    else next.delete(id);
    this.expandedIds.set(next);
  }
}
