import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { LucideCompass, LucideFileText, LucideLayoutDashboard } from '@lucide/angular';
import { MmThemePicker, ThemeService } from '@app/ui';

import { AutomationServiceStatus } from './automation/automation.models';
import {
  resolveServiceHref,
  visibleServiceCatalog,
} from './automation/service-catalog';
import { ServiceHealthFacade } from './automation/service-health.facade';
import { SERVICE_LINK_BASES } from './media-stack/media-stack-api.providers';
import { environment } from '../environments/environment';

type ServiceStatus = 'healthy' | 'degraded' | 'offline' | 'unknown';

interface ServiceNavItem {
  id: string;
  name: string;
  initial: string;
  href: string | null;
  status: ServiceStatus;
  statusLabel: string;
}

const STATUS_LABEL: Record<ServiceStatus, string> = {
  healthy: 'Healthy',
  degraded: 'Degraded',
  offline: 'Offline',
  unknown: 'Unknown',
};

@Component({
  selector: 'app-root',
  imports: [NgTemplateOutlet, RouterLink, RouterLinkActive, RouterOutlet, MmThemePicker, LucideLayoutDashboard, LucideFileText, LucideCompass],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  readonly themeService = inject(ThemeService);
  private readonly health = inject(ServiceHealthFacade);
  private readonly linkBases = inject(SERVICE_LINK_BASES);
  readonly modeLabel = environment.modeLabel;

  private readonly serviceCatalog: Omit<ServiceNavItem, 'status' | 'statusLabel'>[] =
    visibleServiceCatalog(environment.useLiveApi).map((entry) => ({
      id: entry.id,
      name: entry.name,
      initial: entry.initial,
      href: resolveServiceHref(entry.id, this.linkBases),
    }));

  readonly services = computed(() => {
    const liveById = new Map(this.health.services().map((service) => [service.id, service]));
    return this.serviceCatalog.map((item) => {
      const live = liveById.get(item.id);
      const status = live ? mapLiveStatus(live.status) : 'unknown';
      return {
        ...item,
        status,
        statusLabel: STATUS_LABEL[status],
      };
    });
  });

  constructor() {
    this.health.startPolling();
  }
}

function mapLiveStatus(status: AutomationServiceStatus): ServiceStatus {
  if (status === 'healthy') return 'healthy';
  if (status === 'degraded') return 'degraded';
  if (status === 'down') return 'offline';
  return 'unknown';
}
