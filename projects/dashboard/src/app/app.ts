import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { LucideCompass, LucideFileText, LucideLayoutDashboard } from '@lucide/angular';
import { MmThemePicker, ThemeService } from '@app/ui';

import { environment } from '../environments/environment';

type ServiceStatus = 'healthy' | 'degraded' | 'offline';

interface ServiceNavItem {
  id: string;
  name: string;
  initial: string;
  href: string | null;
  status: ServiceStatus;
  statusLabel: string;
}

@Component({
  selector: 'app-root',
  imports: [RouterLink, RouterLinkActive, RouterOutlet, MmThemePicker, LucideLayoutDashboard, LucideFileText, LucideCompass],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  readonly themeService = inject(ThemeService);
  readonly modeLabel = environment.modeLabel;

  readonly services: ServiceNavItem[] = ((): ServiceNavItem[] => {
    const items: ServiceNavItem[] = [
      { id: 'jellyfin', name: 'Jellyfin', initial: 'J', href: null, status: 'healthy', statusLabel: 'Healthy' },
      { id: 'sonarr', name: 'Sonarr', initial: 'S', href: null, status: 'healthy', statusLabel: 'Healthy' },
      { id: 'radarr', name: 'Radarr', initial: 'R', href: null, status: 'healthy', statusLabel: 'Healthy' },
      { id: 'prowlarr', name: 'Prowlarr', initial: 'P', href: null, status: 'degraded', statusLabel: 'Degraded' },
      { id: 'qbittorrent', name: 'qBittorrent', initial: 'q', href: null, status: 'healthy', statusLabel: 'Healthy' },
      { id: 'bazarr', name: 'Bazarr', initial: 'B', href: null, status: 'healthy', statusLabel: 'Healthy' },
    ];
    if (!environment.useLiveApi) {
      items.splice(4, 0, { id: 'sabnzbd', name: 'SABnzbd', initial: 'S', href: null, status: 'offline', statusLabel: 'Offline' });
    }
    return items;
  })();
}
