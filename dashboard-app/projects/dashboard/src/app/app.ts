import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
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
import { MmProgress, MmToastHost } from '@app/ui';
import { environment } from '../environments/environment';

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
    MmProgress,
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
  private readonly health = inject(ServiceHealthFacade);
  private readonly calendar = inject(CalendarFacade);
  private readonly automation = inject(AutomationFacade);
  private readonly activity = inject(ActivityFacade);
  readonly storage = inject(StorageFacade);
  private readonly libraryItems = inject(LibraryItemsFacade);
  readonly modeLabel = environment.modeLabel;
  readonly shortcutLabel = navigator.platform.toLowerCase().includes('mac') ? '⌘K' : 'Ctrl+K';
  readonly libraryCount = computed(() => this.libraryItems.totalCount());
  readonly commandPaletteOpen = signal(false);
  readonly rightRailOpen = signal(true);

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
    // App owns polling for the shell's long-lived facades.
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

  toggleRightRail(): void {
    this.rightRailOpen.update((open) => !open);
  }

  onAddMedia(): void {
    this.openCommandPalette();
  }
}
