import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MmButton, MmStateCard, MmStatus } from 'media-ui';
import { DiscoverFeedback, DiscoverSourceTab, JellyseerrDiscoverKind, TraktDiscoverType } from '../downloads/media-stack-api';
import { DiscoverCard } from './discover-card';
import { DiscoverHistoryFilter } from './discover-format';
import { DiscoverFacade, HermesView } from './discover.facade';

@Component({
  standalone: true,
  selector: 'mm-discover-page',
  imports: [MmButton, MmStateCard, MmStatus, DiscoverCard],
  providers: [DiscoverFacade],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="page-intro">
      <p class="eyebrow">Workspace</p>
      <h1>Discover</h1>
      <p class="lede">Explore Hermes, Jellyseerr, and Trakt picks, leave feedback, and request eligible titles.</p>
    </section>

    <div class="toolbar">
      <div class="tabs" role="tablist" aria-label="Discover sources">
        @for (tab of tabs; track tab.id) {
          <button
            type="button"
            role="tab"
            class="tab"
            [attr.aria-selected]="facade.tab() === tab.id"
            (click)="setTab(tab.id)"
          >
            {{ tab.label }}
          </button>
        }
      </div>
      <div class="toolbar-actions">
        @if (facade.tab() === 'hermes') {
          <mm-button
            label="Request more"
            variant="quiet"
            [disabled]="facade.requestingMore() || facade.generationPending()"
            [busy]="facade.requestingMore()"
            (click)="requestMore()"
          />
        }
        <mm-button label="Refresh" variant="quiet" (click)="refresh()" />
      </div>
    </div>

    @if (facade.tab() === 'hermes') {
      <div class="filters" aria-label="Hermes filters">
        <div class="filter-group" role="group" aria-label="Hermes view">
          @for (view of hermesViews; track view.id) {
            <button type="button" class="chip" [attr.aria-pressed]="facade.hermesView() === view.id" (click)="setHermesView(view.id)">
              {{ view.label }}
            </button>
          }
        </div>
        @if (facade.hermesView() === 'history') {
          <div class="filter-group" role="group" aria-label="History filter">
            @for (filter of historyFilters; track filter.id) {
              <button
                type="button"
                class="chip"
                [attr.aria-pressed]="facade.historyFilter() === filter.id"
                (click)="setHistoryFilter(filter.id)"
              >
                {{ filter.label }}
              </button>
            }
          </div>
        }
      </div>
    }

    @if (facade.tab() === 'jellyseerr') {
      <div class="filters" role="group" aria-label="Jellyseerr kind">
        @for (kind of jellyseerrKinds; track kind.id) {
          <button type="button" class="chip" [attr.aria-pressed]="facade.jellyseerrKind() === kind.id" (click)="setJellyseerrKind(kind.id)">
            {{ kind.label }}
          </button>
        }
      </div>
    }

    @if (facade.tab() === 'trakt') {
      <div class="filters" role="group" aria-label="Trakt type">
        @for (type of traktTypes; track type.id) {
          <button type="button" class="chip" [attr.aria-pressed]="facade.traktType() === type.id" (click)="setTraktType(type.id)">
            {{ type.label }}
          </button>
        }
      </div>
    }

    @if (facade.notice()) {
      <p class="notice" role="status" aria-live="polite">
        <mm-status [tone]="facade.noticeTone()">{{ facade.notice() }}</mm-status>
      </p>
    }

    @if (facade.status() === 'loading') {
      <mm-state-card icon="◌" title="Loading discover" message="Fetching recommendations…" />
    } @else if (facade.status() === 'error') {
      <mm-state-card icon="!" title="Discover unavailable" [message]="facade.error()" tone="danger">
        <mm-button label="Try again" (click)="refresh()" />
      </mm-state-card>
    } @else if (facade.status() === 'empty') {
      <mm-state-card icon="∅" title="Nothing to show" message="No titles match this source and filter yet." />
    } @else {
      <div class="grid" aria-live="polite">
        @for (item of facade.visibleItems(); track item.id) {
          <mm-discover-card
            [item]="item"
            [showFeedback]="facade.tab() === 'hermes'"
            [syncFailed]="facade.isSyncFailed(item.id)"
            [busy]="facade.busyItemId() === item.id"
            (feedback)="onFeedback(item.id, $event)"
            (request)="onRequest(item)"
          />
        }
      </div>
    }
  `,
  styles: `
    :host { display: block; }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      margin: 28px 0 16px;
    }
    .tabs, .filters, .filter-group, .toolbar-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .filters { margin-bottom: 16px; }
    .tab, .chip {
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-sm);
      padding: 8px 12px;
      background: var(--mm-component-control-bg);
      color: var(--mm-component-text-primary);
      cursor: pointer;
      font: 700 13px/1 var(--mm-font-body);
    }
    .tab[aria-selected='true'], .chip[aria-pressed='true'] {
      border-color: var(--mm-component-accent);
      color: var(--mm-component-accent);
    }
    .notice { margin: 0 0 14px; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 18px;
    }
  `,
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
