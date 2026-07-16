import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { LucideSettings } from '@lucide/angular';
import { MmButton, MmCard, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { AutomationService, AutomationServiceStatus } from './automation.models';
import { AutomationFacade } from './automation.facade';
import { AUTOMATION_SERVICE_STATUS_VIEW, AutomationStatusView, formatRelativeTime } from './automation-format';

const SERVICE_STATUS_RANK: Record<AutomationServiceStatus, number> = {
  down: 0,
  degraded: 1,
  unknown: 2,
  healthy: 3,
};

@Component({
  selector: 'mm-automation-board',
  imports: [MmButton, MmCard, MmSkeleton, MmStateCard, MmStatus, LucideSettings],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './automation-board.html',
  styleUrl: './automation-board.scss',
})
export class AutomationBoard {
  readonly facade = inject(AutomationFacade);
  readonly rowSkeletons = [0, 1, 2];
  readonly formatRelativeTime = formatRelativeTime;
  readonly sortedServices = computed(() => this.sortServices(this.facade.summary()?.services ?? []));
  readonly partialMessage = computed(() => {
    const summary = this.facade.summary();
    const names: string[] = [];
    if (this.facade.summaryUnavailable()) names.push('automation summary');
    if (summary?.availability.services === 'unavailable') names.push('services');
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

  private joinNames(names: string[]): string {
    const capitalized = names.map((name) => name.charAt(0).toUpperCase() + name.slice(1));
    if (capitalized.length === 1) return `${capitalized[0]} is`;
    const head = capitalized.slice(0, -1).join(', ');
    const tail = capitalized[capitalized.length - 1];
    return `${head} and ${tail} are`;
  }
}
