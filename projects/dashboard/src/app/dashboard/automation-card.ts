import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { LucideChevronRight } from '@lucide/angular';
import {
  MmButton,
  MmDialog,
  MmDialogTone,
  MmProgress,
  MmSkeleton,
  MmStateCard,
  MmStatus,
} from '@app/ui';
import {
  AutomationProblemSeverity,
  AutomationService,
  AutomationServiceStatus,
  compareAutomationServices,
} from '../automation/automation.models';
import {
  AUTOMATION_PROBLEM_SEVERITY_VIEW,
  AUTOMATION_SERVICE_STATUS_VIEW,
} from '../automation/automation-format';
import { resolveServiceHref } from '../automation/service-catalog';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { StorageFacade } from '../storage/storage.facade';
import { formatStorageBytes, STORAGE_VOLUME_TONE } from '../storage/storage-format';
import { StorageVolume } from '../storage/storage.models';

const PROBLEM_SEVERITY_RANK: Record<AutomationProblemSeverity, number> = {
  actionable: 0,
  warning: 1,
  info: 2,
};

const PROBLEM_SEVERITY_ORDER: AutomationProblemSeverity[] = ['actionable', 'warning', 'info'];

@Component({
  selector: 'mm-automation-card',
  imports: [
    MmButton,
    MmDialog,
    MmProgress,
    MmSkeleton,
    MmStateCard,
    MmStatus,
    RouterLink,
    LucideChevronRight,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './automation-card.html',
  styleUrl: './automation-card.scss',
})
export class AutomationCard {
  readonly health = inject(ServiceHealthFacade);
  readonly storage = inject(StorageFacade);
  private readonly linkBases = inject(SERVICE_LINK_BASES);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly serviceDialog = viewChild.required<MmDialog>('serviceDialog');

  readonly skeletonRows = [0, 1, 2, 3];
  readonly formatBytes = formatStorageBytes;

  readonly selectedService = signal<AutomationService | null>(null);

  readonly flaggedServices = computed(() =>
    this.health
      .services()
      .filter((service) => service.status !== 'healthy')
      .sort(compareAutomationServices),
  );

  readonly healthyServices = computed(() =>
    this.health.services().filter((service) => service.status === 'healthy'),
  );

  readonly selectedProblems = computed(() => {
    const serviceId = this.selectedService()?.id;
    if (!serviceId) return [];
    return this.health
      .problems()
      .filter((problem) => problem.serviceId === serviceId)
      .sort((left, right) => PROBLEM_SEVERITY_RANK[left.severity] - PROBLEM_SEVERITY_RANK[right.severity]);
  });

  readonly selectedProblemGroups = computed(() =>
    PROBLEM_SEVERITY_ORDER.map((severity) => ({
      severity,
      label: AUTOMATION_PROBLEM_SEVERITY_VIEW[severity].label,
      problems: this.selectedProblems().filter((problem) => problem.severity === severity),
    })).filter((group) => group.problems.length > 0),
  );

  readonly libraryVolume = computed(() => {
    const volumes = this.storage.volumes();
    const library = volumes.find((volume) => volume.kind === 'library');
    if (library) return library;
    return volumes.length > 0 ? volumes[0] : null;
  });

  constructor() {
    this.storage.startPolling();
  }

  statusLabel(status: AutomationServiceStatus): string {
    return AUTOMATION_SERVICE_STATUS_VIEW[status].label;
  }

  dialogTone(status: AutomationServiceStatus | undefined): MmDialogTone {
    if (status === 'down') return 'danger';
    if (status === 'degraded') return 'warning';
    return 'default';
  }

  serviceHref(id: string): string | null {
    return resolveServiceHref(id, this.linkBases);
  }

  openService(service: AutomationService): void {
    this.selectedService.set(service);
    // Paint title/body before showModal so the first announcement is not stale.
    this.cdr.detectChanges();
    this.serviceDialog().open();
  }

  onDialogClosed(): void {
    this.selectedService.set(null);
  }

  barTone(volume: StorageVolume) {
    return STORAGE_VOLUME_TONE[volume.kind];
  }

  percent(volume: StorageVolume): number {
    if (!volume.totalBytes) return 0;
    return Math.min(100, Math.round((volume.usedBytes / volume.totalBytes) * 100));
  }

  retryHealth(): void {
    void this.health.refresh();
  }

  retryStorage(): void {
    void this.storage.refresh({ initial: true });
  }
}
