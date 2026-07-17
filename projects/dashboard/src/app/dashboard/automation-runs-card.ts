import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LucideChevronRight, LucideClock } from '@lucide/angular';
import { MmButton, MmCard, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { AutomationFacade } from '../automation/automation.facade';
import { CronRun } from '../reports/reports.models';
import { cronStatusView } from '../reports/reports-format';
import { formatRelativeTime } from '../automation/automation-format';

@Component({
  selector: 'mm-automation-runs-card',
  imports: [MmButton, MmCard, MmSkeleton, MmStateCard, MmStatus, RouterLink, LucideClock, LucideChevronRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './automation-runs-card.html',
  styleUrl: './automation-runs-card.scss',
})
export class AutomationRunsCard {
  readonly facade = inject(AutomationFacade);
  readonly skeletonRows = [0, 1, 2];
  readonly statusView = cronStatusView;
  readonly formatRelativeTime = formatRelativeTime;

  constructor() {
    this.facade.startPolling();
  }

  jobMeta(run: CronRun): string {
    // Lightweight grouping label; expand if schedule metadata becomes richer.
    return run.schedule || 'Automation';
  }

  retry(): void {
    void this.facade.refresh();
  }
}
