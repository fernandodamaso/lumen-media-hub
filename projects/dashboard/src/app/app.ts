import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { LucideCompass, LucideFileText, LucideLayoutDashboard } from '@lucide/angular';
import { MmThemePicker, ThemeService } from '@app/ui';

import { AutomationServiceStatus } from './automation/automation.models';
import { ServiceHealthFacade } from './automation/service-health.facade';
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
  imports: [RouterLink, RouterLinkActive, RouterOutlet, MmThemePicker, LucideLayoutDashboard, LucideFileText, LucideCompass],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  readonly themeService = inject(ThemeService);
  private readonly health = inject(ServiceHealthFacade);
  readonly modeLabel = environment.modeLabel;

  private readonly serviceCatalog: Omit<ServiceNavItem, 'status' | 'statusLabel'>[] = (() => {
    const items: Omit<ServiceNavItem, 'status' | 'statusLabel'>[] = [
      { id: 'jellyfin', name: 'Jellyfin', initial: 'J', href: null },
      { id: 'sonarr', name: 'Sonarr', initial: 'S', href: null },
      { id: 'radarr', name: 'Radarr', initial: 'R', href: null },
      { id: 'prowlarr', name: 'Prowlarr', initial: 'P', href: null },
      { id: 'qbittorrent', name: 'qBittorrent', initial: 'q', href: null },
      { id: 'bazarr', name: 'Bazarr', initial: 'B', href: null },
    ];
    if (!environment.useLiveApi) {
      items.splice(4, 0, { id: 'sabnzbd', name: 'SABnzbd', initial: 'S', href: null });
    }
    return items;
  })();

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
