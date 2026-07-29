import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MmButton, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { DiscoverFeedback, DiscoverSourceTab, JellyseerrDiscoverKind, TraktDiscoverType } from './discover.models';
import { DiscoverCard } from './discover-card';
import { DiscoverHistoryFilter, matchesDiscoverSearch } from './discover-format';
import { DiscoverFacade, HermesView } from './discover.facade';

export const DISCOVER_BATCH_SIZE = 24;

@Component({
  selector: 'mm-discover-page',
  imports: [MmButton, MmSkeleton, MmStateCard, MmStatus, DiscoverCard],
  providers: [DiscoverFacade],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './discover-page.html',
  styleUrl: './discover-page.scss',
})
export class DiscoverPage {
  readonly facade = inject(DiscoverFacade);

  readonly DISCOVER_BATCH_SIZE = DISCOVER_BATCH_SIZE;

  readonly searchQuery = signal('');
  readonly visibleLimit = signal(DISCOVER_BATCH_SIZE);

  readonly filteredItems = computed(() =>
    this.facade.visibleItems().filter((item) => matchesDiscoverSearch(item, this.searchQuery())),
  );

  readonly displayedItems = computed(() => this.filteredItems().slice(0, this.visibleLimit()));

  readonly remainingCount = computed(() =>
    Math.max(0, this.filteredItems().length - this.displayedItems().length),
  );

  readonly resultCountLabel = computed(() => {
    const count = this.filteredItems().length;
    const query = this.searchQuery().trim();
    if (!query) {
      return count === 1 ? '1 title' : `${count} titles`;
    }
    return count === 1 ? '1 match' : `${count} matches`;
  });

  readonly hasSearchQuery = computed(() => this.searchQuery().trim().length > 0);

  readonly loadMoreLabel = computed(() => {
    const count = Math.min(DISCOVER_BATCH_SIZE, this.remainingCount());
    return `Load ${count} more`;
  });

  readonly skeletonSlots = Array.from({ length: 12 }, (_, index) => index);

  readonly tabs: { id: DiscoverSourceTab; label: string }[] = [
    { id: 'hermes', label: 'Hermes' },
    { id: 'jellyseerr', label: 'Jellyseerr' },
    { id: 'trakt', label: 'Trakt' },
  ];
  readonly hermesViews: { id: HermesView; label: string }[] = [
    { id: 'active', label: 'Active' },
    { id: 'history', label: 'History' },
  ];
  readonly historyFilters: { id: DiscoverHistoryFilter; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'liked', label: 'Liked' },
    { id: 'disliked', label: 'Disliked' },
    { id: 'watched', label: 'Watched' },
    { id: 'skipped', label: 'Skipped' },
    { id: 'requested', label: 'Requested' },
  ];
  readonly jellyseerrKinds: { id: JellyseerrDiscoverKind; label: string }[] = [
    { id: 'trending', label: 'Trending' },
    { id: 'movies', label: 'Movies' },
    { id: 'tv', label: 'TV' },
  ];
  readonly traktTypes: { id: TraktDiscoverType; label: string }[] = [
    { id: 'movies', label: 'Movies' },
    { id: 'shows', label: 'Shows' },
  ];

  constructor() {
    void this.facade.setTab('hermes');
  }

  private withLimitReset(changed: boolean, run: () => void): void {
    if (changed) {
      this.resetVisibleLimit();
    }
    run();
  }

  setTab(tab: DiscoverSourceTab): void {
    this.withLimitReset(this.facade.tab() !== tab, () => {
      void this.facade.setTab(tab);
    });
  }

  setHermesView(view: HermesView): void {
    this.withLimitReset(this.facade.hermesView() !== view, () => {
      this.facade.setHermesView(view);
    });
  }

  setHistoryFilter(filter: DiscoverHistoryFilter): void {
    this.withLimitReset(this.facade.historyFilter() !== filter, () => {
      this.facade.setHistoryFilter(filter);
    });
  }

  setJellyseerrKind(kind: JellyseerrDiscoverKind): void {
    this.withLimitReset(this.facade.jellyseerrKind() !== kind, () => {
      this.facade.setJellyseerrKind(kind);
    });
  }

  setTraktType(type: TraktDiscoverType): void {
    this.withLimitReset(this.facade.traktType() !== type, () => {
      this.facade.setTraktType(type);
    });
  }

  setSearchQuery(value: string): void {
    const previous = this.searchQuery().trim();
    this.searchQuery.set(value);
    if (previous !== value.trim()) {
      this.resetVisibleLimit();
    }
  }

  clearSearch(): void {
    if (!this.searchQuery()) return;
    this.searchQuery.set('');
    this.resetVisibleLimit();
  }

  loadMore(): void {
    this.visibleLimit.update((limit) => limit + DISCOVER_BATCH_SIZE);
  }

  resetVisibleLimit(): void {
    this.visibleLimit.set(DISCOVER_BATCH_SIZE);
  }

  refresh(): void {
    void this.facade.setTab(this.facade.tab());
  }

  requestMore(): void {
    void this.facade.requestMore();
  }

  onFeedback(id: string, feedback: DiscoverFeedback): void {
    void this.facade.submitFeedback(id, feedback);
  }

  onRequest(item: ReturnType<DiscoverFacade['visibleItems']>[number]): void {
    void this.facade.requestItem(item);
  }
}
