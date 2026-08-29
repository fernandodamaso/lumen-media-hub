import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  effect,
  ElementRef,
  HostListener,
  inject,
  Injector,
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
import { RecentlyAvailableFacade } from '../library/recently-available.facade';
import { WatchNextFacade } from '../library/watch-next.facade';
import { LibraryStatsFacade } from '../library/library-stats.facade';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { StorageFacade } from '../storage/storage.facade';
import { ActivityFacade } from '../right-rail/activity.facade';
import { refreshDashboardData } from '../dashboard/dashboard-refresh';
import { TrendingFacade } from '../dashboard/trending.facade';
import { MmDialog } from '@app/ui';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { MediaSearchItem } from '../media-request/media-request.models';
import {
  MediaRequestCompletion,
  MediaRequestDialog,
} from '../media-request/media-request-dialog/media-request-dialog';
import { RequestableMediaItem } from '../media-request/media-request.models';

export type CommandPaletteItem = {
  id: string;
  group: 'Routes' | 'Your Library' | 'Catalog' | 'Actions';
  title: string;
  meta: string;
  disabled?: boolean;
  closeOnRun?: boolean;
  run: () => void | Promise<void>;
};

const LIBRARY_QUERY_MIN_CHARS = 2;
const LIBRARY_RESULT_CAP = 40;
const REMOTE_SEARCH_DEBOUNCE_MS = 250;

@Component({
  selector: 'mm-command-palette',
  imports: [MmDialog, MediaRequestDialog],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './command-palette.html',
  styleUrl: './command-palette.scss',
})
export class CommandPalette {
  private readonly router = inject(Router);
  private readonly injector = inject(Injector);
  private readonly libraryItems = inject(LibraryItemsFacade);
  private readonly jellyfinBases = inject(JELLYFIN_LINK_BASES);
  private readonly serviceBases = inject(SERVICE_LINK_BASES);
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);

  readonly open = input(false);
  readonly openChange = output<boolean>();

  readonly query = signal('');
  readonly activeIndex = signal(0);
  readonly searchStatus = signal<string | null>(null);
  readonly requestDialogItem = signal<RequestableMediaItem | null>(null);
  readonly requestDialogOpen = signal(false);
  private readonly remoteMediaItems = signal<MediaSearchItem[] | null>(null);
  private readonly inputRef = viewChild<ElementRef<HTMLInputElement>>('paletteInput');
  private previousOpen = false;
  private searchTimer: ReturnType<typeof setTimeout> | null = null;
  private searchAbort: AbortController | null = null;
  private searchGeneration = 0;

  constructor() {
    effect(() => {
      const isOpen = this.open();
      if (isOpen && !this.previousOpen) {
        this.cancelRemoteSearch();
        this.searchGeneration += 1;
        this.query.set('');
        this.activeIndex.set(0);
        this.remoteMediaItems.set(null);
        this.searchStatus.set(null);
        this.requestDialogOpen.set(false);
        this.requestDialogItem.set(null);
        queueMicrotask(() => this.inputRef()?.nativeElement.focus());
      } else if (!isOpen && this.previousOpen) {
        this.cancelRemoteSearch();
        this.searchGeneration += 1;
      }
      this.previousOpen = isOpen;
    });
    this.destroyRef.onDestroy(() => {
      this.cancelRemoteSearch();
    });
  }

  readonly items = computed(() => {
    const q = this.query().trim().toLowerCase();
    const staticItems = this.staticItems().filter((item) => matchesQuery(item, q));
    if (q.length < LIBRARY_QUERY_MIN_CHARS) return staticItems;

    const authoritativeItems = this.remoteMediaItems();
    if (authoritativeItems !== null) {
      return [...staticItems, ...authoritativeItems.map((item) => this.toRemoteMediaCommand(item))];
    }

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

  readonly activeOptionId = computed(() =>
    this.items().length ? this.optionId(this.activeIndex()) : null,
  );

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
            health: this.injector.get(ServiceHealthFacade),
            libraryItems: this.libraryItems,
            libraryStats: this.injector.get(LibraryStatsFacade),
            watchNext: this.injector.get(WatchNextFacade),
            recentlyAvailable: this.injector.get(RecentlyAvailableFacade),
            downloads: this.injector.get(DownloadsFacade),
            storage: this.injector.get(StorageFacade),
            calendar: this.injector.get(CalendarFacade),
            automation: this.injector.get(AutomationFacade),
            activity: this.injector.get(ActivityFacade),
            trending: this.injector.get(TrendingFacade),
          }),
      },
      {
        id: 'action-pause',
        group: 'Actions',
        title: 'Pause all',
        meta: 'Pause downloads',
        run: () => this.injector.get(DownloadsFacade).runAction('pause'),
      },
      {
        id: 'action-resume',
        group: 'Actions',
        title: 'Resume all',
        meta: 'Resume downloads',
        run: () => this.injector.get(DownloadsFacade).runAction('resume'),
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
      group: 'Your Library',
      title: item.title,
      meta: item.meta || item.kind,
      run: () => {
        const href = item.href ?? resolveJellyfinItemLink(item, this.jellyfinBases);
        if (href) window.open(href, '_blank', 'noreferrer');
        else void this.router.navigateByUrl('/library');
      },
    };
  }

  private toRemoteMediaCommand(item: MediaSearchItem): CommandPaletteItem {
    const href = item.status === 'available'
      ? item.serviceHref ?? resolveJellyfinItemLink(
          { id: item.jellyfinId ?? 'unknown', playable: true },
          this.jellyfinBases,
        )
      : item.serviceHref;
    const disabled = item.status === 'requested' || item.status === 'processing' || item.status === 'unknown';
    const requestable = item.status === 'missing';
    return {
      id: `media-${item.identity}`,
      group: item.status === 'available' ? 'Your Library' : 'Catalog',
      title: item.title,
      meta: [
        item.year,
        item.type === 'tv' ? 'TV' : 'Movie',
        lifecycleDescription(item),
      ].filter(Boolean).join(' · '),
      disabled,
      closeOnRun: !requestable,
      run: () => {
        if (requestable) {
          this.requestDialogItem.set({
            identity: item.identity,
            type: item.type,
            tmdbId: item.tmdbId,
            title: item.title,
            year: item.year,
            posterUrl: item.posterUrl,
          });
          this.requestDialogOpen.set(true);
          return;
        }
        if (href && (item.status === 'available' || item.status === 'tracked')) {
          window.open(href, '_blank', 'noreferrer');
        }
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
    const value = (event.target as HTMLInputElement).value;
    this.query.set(value);
    this.activeIndex.set(0);
    this.scheduleRemoteSearch(value);
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
    if (!item || item.disabled) return;
    if (item.closeOnRun !== false) this.setOpen(false);
    await item.run();
  }

  optionId(index: number): string {
    return `command-palette-option-${index}`;
  }

  async selectItem(item: CommandPaletteItem): Promise<void> {
    if (item.disabled) return;
    if (item.closeOnRun !== false) this.setOpen(false);
    await item.run();
  }

  async onRequestCompleted(completion: MediaRequestCompletion): Promise<void> {
    this.requestDialogOpen.set(false);
    const query = this.query().trim();
    if (query.length < LIBRARY_QUERY_MIN_CHARS || !this.open()) return;
    this.cancelRemoteSearch();
    const generation = ++this.searchGeneration;
    await this.runRemoteSearch(query, generation, completion.identity);
  }

  private scheduleRemoteSearch(query: string): void {
    this.cancelRemoteSearch();
    const generation = ++this.searchGeneration;
    this.remoteMediaItems.set(null);
    this.searchStatus.set(null);
    const trimmed = query.trim();
    if (trimmed.length < LIBRARY_QUERY_MIN_CHARS) return;
    this.searchTimer = setTimeout(() => {
      this.searchTimer = null;
      void this.runRemoteSearch(trimmed, generation);
    }, REMOTE_SEARCH_DEBOUNCE_MS);
  }

  private async runRemoteSearch(
    trimmed: string,
    generation: number,
    selectedIdentity?: string,
  ): Promise<void> {
    const controller = new AbortController();
    this.searchAbort = controller;
    this.searchStatus.set('Searching catalog…');
    try {
      const result = await this.api.searchMedia(trimmed, controller.signal);
      if (
        controller.signal.aborted ||
        generation !== this.searchGeneration ||
        this.query().trim() !== trimmed
      ) {
        return;
      }
      if (result.ok && result.availability === 'available') {
        this.remoteMediaItems.set(result.items);
        this.searchStatus.set(null);
        const selectedIndex = selectedIdentity
          ? this.items().findIndex((item) => item.id === `media-${selectedIdentity}`)
          : -1;
        this.activeIndex.set(selectedIndex >= 0 ? selectedIndex : 0);
      } else if (result.availability === 'disabled') {
        this.searchStatus.set('Catalog search is disabled. Showing local library matches.');
      } else {
        this.searchStatus.set('Catalog search is temporarily unavailable. Showing local library matches.');
      }
    } catch {
      if (
        !controller.signal.aborted &&
        generation === this.searchGeneration &&
        this.query().trim() === trimmed
      ) {
        this.searchStatus.set('Catalog search is temporarily unavailable. Showing local library matches.');
      }
    } finally {
      if (this.searchAbort === controller) this.searchAbort = null;
    }
  }

  private cancelRemoteSearch(): void {
    if (this.searchTimer !== null) {
      clearTimeout(this.searchTimer);
      this.searchTimer = null;
    }
    this.searchAbort?.abort();
    this.searchAbort = null;
  }
}

function lifecycleDescription(item: MediaSearchItem): string {
  switch (item.status) {
    case 'available':
      return 'Available in Jellyfin';
    case 'requested':
      return 'Request submitted';
    case 'processing':
      return 'Acquisition in progress';
    case 'tracked':
      return item.service === 'sonarr' ? 'Tracked in Sonarr' : 'Tracked in Radarr';
    case 'missing':
      return 'Request this title';
    default:
      return 'Status unavailable';
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
