import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import {
  LucideCompass,
  LucideFileText,
  LucideLayoutDashboard,
  LucideLibrary,
  LucideSearch,
} from '@lucide/angular';

import { ServiceHealthFacade } from './automation/service-health.facade';
import { CommandPalette } from './command-palette/command-palette';
import { LibraryItemsFacade } from './library/library-items.facade';
import { environment } from '../environments/environment';

@Component({
  selector: 'app-root',
  imports: [
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    CommandPalette,
    LucideLayoutDashboard,
    LucideLibrary,
    LucideFileText,
    LucideCompass,
    LucideSearch,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  private readonly health = inject(ServiceHealthFacade);
  private readonly libraryItems = inject(LibraryItemsFacade);
  readonly modeLabel = environment.modeLabel;
  readonly shortcutLabel = navigator.platform.toLowerCase().includes('mac') ? '⌘K' : 'Ctrl+K';
  readonly libraryCount = computed(() => this.libraryItems.totalCount());
  readonly commandPaletteOpen = signal(false);

  readonly hasAttention = computed(
    () =>
      this.health.problems().length > 0 ||
      this.health.health().overall === 'down' ||
      this.health.health().overall === 'degraded',
  );

  readonly attentionLabel = computed(() => {
    const attentionServiceIds = new Set(
      this.health
        .services()
        .filter((service) => service.status === 'down' || service.status === 'degraded')
        .map((service) => service.id),
    );
    for (const problem of this.health.problems()) {
      if (problem.serviceId) attentionServiceIds.add(problem.serviceId);
    }
    const count = attentionServiceIds.size;
    return `${count} service${count === 1 ? '' : 's'} need attention`;
  });

  constructor() {
    this.health.startPolling();
  }

  openCommandPalette(): void {
    // Force false→true so the palette resets query/focus even when already open.
    this.commandPaletteOpen.set(false);
    queueMicrotask(() => {
      this.commandPaletteOpen.set(true);
    });
  }
}
