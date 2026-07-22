import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LucideActivity, LucideChevronRight, LucideSettings } from '@lucide/angular';
import { MmButton, MmCard, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { AutomationService, AutomationServiceStatus } from '../automation/automation.models';
import { resolveServiceHref } from '../automation/service-catalog';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { AUTOMATION_SERVICE_STATUS_VIEW } from '../automation/automation-format';

@Component({
  selector: 'mm-service-health-card',
  imports: [
    NgTemplateOutlet,
    MmButton,
    MmCard,
    MmSkeleton,
    MmStateCard,
    MmStatus,
    RouterLink,
    LucideActivity,
    LucideChevronRight,
    LucideSettings,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './service-health-card.html',
  styleUrl: './service-health-card.scss',
})
export class ServiceHealthCard {
  readonly facade = inject(ServiceHealthFacade);
  private readonly linkBases = inject(SERVICE_LINK_BASES);
  readonly skeletonRows = [0, 1, 2, 3];

  constructor() {
    this.facade.startPolling();
  }

  statusLabel(status: AutomationServiceStatus): string {
    return AUTOMATION_SERVICE_STATUS_VIEW[status].label;
  }

  statusDetail(service: AutomationService): string {
    if (service.status === 'healthy') {
      if (typeof service.latencyMs === 'number') return `${service.latencyMs} ms`;
      return service.detail || 'Healthy';
    }
    if (service.status === 'degraded') return service.detail || 'Needs attention';
    return service.detail || 'Unavailable';
  }

  serviceHref(id: string): string | null {
    return resolveServiceHref(id, this.linkBases);
  }

  retry(): void {
    void this.facade.refresh();
  }
}
