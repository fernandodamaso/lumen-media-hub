import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import {
  LucideCompass,
  LucideFileText,
  LucideLayoutDashboard,
  LucideLibrary,
} from '@lucide/angular';

import { ServiceHealthFacade } from './automation/service-health.facade';
import { AutomationFacade } from './automation/automation.facade';
import { CalendarFacade } from './calendar/calendar.facade';
import { CommandPalette } from './command-palette/command-palette';
import { LibraryItemsFacade } from './library/library-items.facade';
import { ActivityFacade } from './right-rail/activity.facade';
import { RightRail } from './right-rail/right-rail';
import { StorageFacade } from './storage/storage.facade';
import { formatStorageBytes } from './storage/storage-format';
import { Topbar } from './topbar/topbar';
import { MmToastHost } from './ui/toast';

@Component({
  selector: 'app-root',
  imports: [
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    CommandPalette,
    RightRail,
    Topbar,
    MmToastHost,
    LucideLayoutDashboard,
    LucideLibrary,
    LucideFileText,
    LucideCompass,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  private readonly router = inject(Router);
  private readonly health = inject(ServiceHealthFacade);
  private readonly calendar = inject(CalendarFacade);
  private readonly automation = inject(AutomationFacade);
  private readonly activity = inject(ActivityFacade);
  readonly storage = inject(StorageFacade);
  private readonly libraryItems = inject(LibraryItemsFacade);
  readonly shortcutLabel = navigator.platform.toLowerCase().includes('mac') ? '⌘K' : 'Ctrl+K';
  readonly libraryCount = computed(() => this.libraryItems.totalCount());
  readonly commandPaletteOpen = signal(false);

  readonly libraryVolume = computed(
    () => this.storage.volumes().find((volume) => volume.kind === 'library') ?? null,
  );

  readonly storagePercent = computed(() => {
    const volume = this.libraryVolume();
    if (!volume || !volume.totalBytes) return 0;
    return Math.min(100, Math.round((volume.usedBytes / volume.totalBytes) * 100));
  });

  readonly storageUsedLabel = computed(() => {
    const volume = this.libraryVolume();
    return volume ? formatStorageBytes(volume.usedBytes) : '';
  });

  readonly storageTotalLabel = computed(() => {
    const volume = this.libraryVolume();
    return volume ? formatStorageBytes(volume.totalBytes) : '';
  });

  constructor() {
    // App owns polling for every shell-consumed facade: sidebar storage, right rail.
    this.health.startPolling();
    this.calendar.startPolling();
    this.automation.startPolling();
    this.storage.startPolling();
    this.activity.startPolling();
  }

  openCommandPalette(): void {
    // Force false→true so the palette resets query/focus even when already open.
    this.commandPaletteOpen.set(false);
    queueMicrotask(() => {
      this.commandPaletteOpen.set(true);
    });
  }

  onAddMedia(): void {
    void this.router.navigate(['/discover']);
  }
}
