import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  ElementRef,
  HostListener,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';
import { AutomationFacade } from '../automation/automation.facade';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { CalendarFacade } from '../calendar/calendar.facade';
import { DownloadsFacade } from '../downloads/downloads.facade';
import { JELLYFIN_LINK_BASES, resolveJellyfinItemLink } from '../library/library.models';
import { LibraryItemsFacade } from '../library/library-items.facade';
import { WatchNextFacade } from '../library/watch-next.facade';
import { LibraryStatsFacade } from '../library/library-stats.facade';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { StorageFacade } from '../storage/storage.facade';
import { refreshDashboardData } from '../dashboard/dashboard-refresh';

export type CommandPaletteItem = {
  id: string;
  group: 'Routes' | 'Library' | 'Actions';
  title: string;
  meta: string;
  run: () => void | Promise<void>;
};

const LIBRARY_QUERY_MIN_CHARS = 2;
const LIBRARY_RESULT_CAP = 40;

@Component({
  selector: 'mm-command-palette',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './command-palette.html',
  styleUrl: './command-palette.scss',
})
export class CommandPalette {
  private readonly router = inject(Router);
  private readonly health = inject(ServiceHealthFacade);
  private readonly libraryItems = inject(LibraryItemsFacade);
  private readonly watchNext = inject(WatchNextFacade);
  private readonly libraryStats = inject(LibraryStatsFacade);
  private readonly downloads = inject(DownloadsFacade);
  private readonly storage = inject(StorageFacade);
  private readonly calendar = inject(CalendarFacade);
  private readonly automation = inject(AutomationFacade);
  private readonly jellyfinBases = inject(JELLYFIN_LINK_BASES);
  private readonly serviceBases = inject(SERVICE_LINK_BASES);

  readonly open = input(false);
  readonly openChange = output<boolean>();

  readonly query = signal('');
  readonly activeIndex = signal(0);
  private readonly inputRef = viewChild<ElementRef<HTMLInputElement>>('paletteInput');
  private previousOpen = false;

  constructor() {
    effect(() => {
      const isOpen = this.open();
      if (isOpen && !this.previousOpen) {
        this.query.set('');
        this.activeIndex.set(0);
        queueMicrotask(() => this.inputRef()?.nativeElement.focus());
      }
      this.previousOpen = isOpen;
    });
  }

  readonly items = computed(() => {
    const q = this.query().trim().toLowerCase();
    const staticItems = this.staticItems().filter((item) => matchesQuery(item, q));
    if (q.length < LIBRARY_QUERY_MIN_CHARS) return staticItems;

    const libraryItems: CommandPaletteItem[] = [];
    for (const item of this.libraryItems.items()) {
      const command = this.toLibraryCommand(item);
      if (!matchesQuery(command, q)) continue;
      libraryItems.push(command);
      if (libraryItems.length >= LIBRARY_RESULT_CAP) break;
    }
    return [...staticItems, ...libraryItems];
  });

  readonly grouped = computed(() => {
    const groups: { name: CommandPaletteItem['group']; items: CommandPaletteItem[] }[] = [];
    for (const item of this.items()) {
      let group = groups.find((entry) => entry.name === item.group);
      if (!group) {
        group = { name: item.group, items: [] };
        groups.push(group);
      }
      group.items.push(item);
    }
    return groups;
  });

  private readonly staticItems = computed(() => {
    const routes: CommandPaletteItem[] = [
      {
        id: 'route-dashboard',
        group: 'Routes',
        title: 'Dashboard',
        meta: 'Home overview',
        run: () => void this.router.navigateByUrl('/'),
      },
      {
        id: 'route-library',
        group: 'Routes',
        title: 'Library',
        meta: 'Browse titles',
        run: () => void this.router.navigateByUrl('/library'),
      },
      {
        id: 'route-reports',
        group: 'Routes',
        title: 'Reports',
        meta: 'Automation activity',
        run: () => void this.router.navigateByUrl('/reports'),
      },
      {
        id: 'route-discover',
        group: 'Routes',
        title: 'Discover',
        meta: 'Find new media',
        run: () => void this.router.navigateByUrl('/discover'),
      },
    ];

    const actions: CommandPaletteItem[] = [
      {
        id: 'action-refresh',
        group: 'Actions',
        title: 'Refresh all',
        meta: 'Reload dashboard data',
        run: () =>
          refreshDashboardData({
            health: this.health,
            libraryItems: this.libraryItems,
            libraryStats: this.libraryStats,
            watchNext: this.watchNext,
            downloads: this.downloads,
            storage: this.storage,
            calendar: this.calendar,
            automation: this.automation,
          }),
      },
      {
        id: 'action-pause',
        group: 'Actions',
        title: 'Pause all',
        meta: 'Pause downloads',
        run: () => this.downloads.runAction('pause'),
      },
      {
        id: 'action-resume',
        group: 'Actions',
        title: 'Resume all',
        meta: 'Resume downloads',
        run: () => this.downloads.runAction('resume'),
      },
      {
        id: 'action-jellyfin',
        group: 'Actions',
        title: 'Open Jellyfin',
        meta: 'External service',
        run: () => {
          const href = this.jellyfinBases.jellyfinBase;
          if (href) window.open(href, '_blank', 'noreferrer');
        },
      },
      {
        id: 'action-qbit',
        group: 'Actions',
        title: 'Open qBittorrent',
        meta: 'External service',
        run: () => {
          const href = this.serviceBases.qbittorrent;
          if (href) window.open(href, '_blank', 'noreferrer');
        },
      },
    ];

    return [...routes, ...actions];
  });

  private toLibraryCommand(item: {
    id: string;
    title: string;
    meta: string;
    kind: string;
    href: string | null;
    playable: boolean;
  }): CommandPaletteItem {
    return {
      id: `library-${item.id}`,
      group: 'Library',
      title: item.title,
      meta: item.meta || item.kind,
      run: () => {
        const href = item.href ?? resolveJellyfinItemLink(item, this.jellyfinBases);
        if (href) window.open(href, '_blank', 'noreferrer');
        else void this.router.navigateByUrl('/library');
      },
    };
  }

  @HostListener('document:keydown', ['$event'])
  onDocumentKeydown(event: KeyboardEvent): void {
    const isPaletteShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k';
    if (isPaletteShortcut) {
      event.preventDefault();
      this.setOpen(!this.open());
      return;
    }
    if (!this.open()) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      this.setOpen(false);
    }
  }

  setOpen(value: boolean): void {
    this.openChange.emit(value);
  }

  onQueryInput(event: Event): void {
    this.query.set((event.target as HTMLInputElement).value);
    this.activeIndex.set(0);
  }

  onListKeydown(event: KeyboardEvent): void {
    const count = this.items().length;
    if (!count) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      this.activeIndex.update((index) => (index + 1) % count);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      this.activeIndex.update((index) => (index - 1 + count) % count);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      void this.selectIndex(this.activeIndex());
    }
  }

  flatIndex(groupIndex: number, itemIndex: number): number {
    let index = 0;
    const groups = this.grouped();
    for (let g = 0; g < groupIndex; g++) index += groups[g].items.length;
    return index + itemIndex;
  }

  async selectIndex(index: number): Promise<void> {
    const item = this.items().at(index);
    if (!item) return;
    this.setOpen(false);
    await item.run();
  }

  async selectItem(item: CommandPaletteItem): Promise<void> {
    this.setOpen(false);
    await item.run();
  }
}

function matchesQuery(item: CommandPaletteItem, query: string): boolean {
  if (!query) return true;
  return (
    item.title.toLowerCase().includes(query) ||
    item.meta.toLowerCase().includes(query) ||
    item.group.toLowerCase().includes(query)
  );
}

