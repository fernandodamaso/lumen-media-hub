import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MmButton, MmStateCard, MmStatus } from '@app/ui';
import { DiscoverFeedback, DiscoverSourceTab, JellyseerrDiscoverKind, TraktDiscoverType } from '../media-stack/media-stack-api';
import { DiscoverCard } from './discover-card';
import { DiscoverHistoryFilter } from './discover-format';
import { DiscoverFacade, HermesView } from './discover.facade';

@Component({
  selector: 'mm-discover-page',
  imports: [MmButton, MmStateCard, MmStatus, DiscoverCard],
  providers: [DiscoverFacade],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './discover-page.html',
  styleUrl: './discover-page.scss',
})
export class DiscoverPage {
  readonly facade = inject(DiscoverFacade);

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
    this.facade.startPolling();
  }

  setTab(tab: DiscoverSourceTab): void {
    this.facade.setTab(tab);
  }

  setHermesView(view: HermesView): void {
    this.facade.setHermesView(view);
  }

  setHistoryFilter(filter: DiscoverHistoryFilter): void {
    this.facade.setHistoryFilter(filter);
  }

  setJellyseerrKind(kind: JellyseerrDiscoverKind): void {
    this.facade.setJellyseerrKind(kind);
  }

  setTraktType(type: TraktDiscoverType): void {
    this.facade.setTraktType(type);
  }

  refresh(): void {
    void this.facade.refresh();
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
