import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MmButton, MmCard, MmPoster, MmSkeleton, MmStateCard } from '@app/ui';
import { LibraryItemKind } from '../media-stack/media-stack-api';
import { LIBRARY_KIND_LABEL, libraryEmptyMessage } from './library-format';
import { LibraryFacade } from './library.facade';

@Component({
  standalone: true,
  selector: 'mm-library-board',
  imports: [MmButton, MmCard, MmPoster, MmSkeleton, MmStateCard],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mm-card class="library" labelledBy="library-heading">
      <div mm-card-header>
        <h2 id="library-heading">Library</h2>
      </div>
      <div mm-card-header-actions class="header-actions">
        <div class="switcher" aria-label="Library collection">
          <button
            type="button"
            class="switcher__tab"
            [class.switcher__tab--active]="facade.kind() === 'movie'"
            [attr.aria-pressed]="facade.kind() === 'movie'"
            (click)="setKind('movie')"
          >
            {{ kindLabel('movie') }}
            <span class="switcher__count">{{ facade.movieCount() }}</span>
          </button>
          <button
            type="button"
            class="switcher__tab"
            [class.switcher__tab--active]="facade.kind() === 'series'"
            [attr.aria-pressed]="facade.kind() === 'series'"
            (click)="setKind('series')"
          >
            {{ kindLabel('series') }}
            <span class="switcher__count">{{ facade.seriesCount() }}</span>
          </button>
        </div>
      </div>

      @if (facade.status() === 'loading') {
        <div class="poster-grid skeleton-grid" aria-hidden="true">
          @for (i of posterSkeletons; track i) {
            <div class="poster-skeleton"><mm-skeleton variant="rect" /></div>
          }
        </div>
      } @else if (facade.status() === 'error') {
        <mm-state-card kind="error" title="Library unavailable" [message]="facade.error()" tone="danger">
          <mm-button label="Try again" (click)="retry()" />
        </mm-state-card>
      } @else if (facade.status() === 'empty') {
        <mm-state-card kind="empty" title="Nothing here" [message]="emptyMessage()" />
      } @else {
        <div class="poster-grid" aria-live="polite">
          @for (item of facade.items(); track item.id) {
            @if (item.href) {
              <a class="poster-card" [attr.data-artwork]="item.artworkState" [href]="item.href" target="_blank" rel="noreferrer" [attr.aria-label]="item.title + ' (opens in a new tab)'">
                <mm-poster [title]="item.title" [meta]="item.meta" [art]="item.art" [rating]="item.rating ?? null" />
              </a>
            } @else {
              <div class="poster-card" [attr.data-artwork]="item.artworkState"><mm-poster [title]="item.title" [meta]="item.meta" [art]="item.art" [rating]="item.rating ?? null" /></div>
            }
          }
        </div>
      }
      <ng-container mm-card-footer>
        @if (facade.status() === 'ready') {
          <span class="library-summary">
            {{ selectedCountLabel() }}
          </span>
        }
      </ng-container>
      <ng-container mm-card-footer-actions>
        @if (facade.viewAllHref(); as href) {
          <a class="view-all" [href]="href" target="_blank" rel="noreferrer">View all ↗</a>
        }
      </ng-container>
    </mm-card>
  `,
  styles: `
    :host { display: block; }
    .header-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    h2 { margin: 0; color: var(--mm-component-text-primary); font-size: var(--mm-text-lg); font-weight: 700; letter-spacing: -0.01em; }
    .switcher {
      display: inline-flex;
      gap: 4px;
      padding: 3px;
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-md);
      background: var(--mm-component-card-bg);
    }
    .switcher__tab {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      gap: 6px;
      border: 0;
      border-radius: var(--mm-radius-sm);
      padding: 3px 9px;
      background: transparent;
      color: var(--mm-component-text-secondary);
      cursor: pointer;
      font: 700 var(--mm-text-sm)/1 var(--mm-font-body);
      transition: background var(--mm-transition-fast), color var(--mm-transition-fast);
    }
    .switcher__tab:hover {
      background: var(--mm-component-muted-bg);
      color: var(--mm-component-text-primary);
    }
    .switcher__tab:focus-visible {
      outline: 3px solid var(--mm-component-focus-ring);
      outline-offset: 2px;
    }
    .switcher__tab--active,
    .switcher__tab[aria-pressed='true'] {
      background: color-mix(in srgb, var(--mm-component-accent) 12%, transparent);
      color: var(--mm-component-accent);
    }
    .switcher__count {
      color: var(--mm-component-text-muted);
      font-variant-numeric: tabular-nums;
    }
    .poster-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(124px, 1fr));
      gap: 12px;
    }
    .poster-card {
      display: block;
      outline: none;
      color: inherit;
      text-decoration: none;
      transition: transform var(--mm-transition-fast), box-shadow var(--mm-transition-fast);
    }
    @media (hover: hover) and (pointer: fine) {
      .poster-card:hover {
        transform: translateY(-2px);
      }
      .poster-card:hover :is(mm-poster) {
        box-shadow: 0 18px 44px rgb(0 0 0 / 28%);
      }
    }
    .poster-card :is(mm-poster) {
      display: block;
      width: 100%;
      max-width: none;
      transition: box-shadow var(--mm-transition-fast);
    }
    .poster-card:nth-child(n+17) { display: none; }
    .poster-skeleton {
      aspect-ratio: 2 / 3;
      border-radius: var(--mm-radius-md);
      overflow: hidden;
    }
    .poster-skeleton mm-skeleton {
      display: block;
      width: 100%;
      height: 100%;
    }
    .library-summary { color: var(--mm-component-text-muted); font-size: var(--mm-text-sm); }
    .view-all { display: inline-flex; align-items: center; min-height: 32px; color: var(--mm-component-accent); font-size: var(--mm-text-md); font-weight: 700; text-decoration: none; }
    .view-all:focus-visible { outline: 3px solid var(--mm-component-focus-ring); outline-offset: 2px; border-radius: var(--mm-radius-sm); }
    .poster-card:focus-visible {
      box-shadow: 0 0 0 2px var(--mm-component-accent);
      border-radius: var(--mm-radius-md);
    }
    @container (max-width: 639px) {
      .poster-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .poster-card:nth-child(n+10) { display: none; }
    }
    @media (max-width: 900px), (pointer: coarse) {
      .switcher__tab { min-height: 36px; padding: 5px 11px; }
    }
  `,
})
export class LibraryBoard {
  readonly facade = inject(LibraryFacade);
  readonly posterSkeletons = [0, 1, 2, 3];

  kindLabel(kind: LibraryItemKind): string {
    return LIBRARY_KIND_LABEL[kind];
  }

  setKind(kind: LibraryItemKind): void {
    this.facade.setKind(kind);
  }

  emptyMessage(): string {
    return libraryEmptyMessage(this.facade.kind());
  }

  selectedCountLabel(): string {
    const isMovie = this.facade.kind() === 'movie';
    const count = isMovie ? this.facade.movieCount() : this.facade.seriesCount();
    const label = isMovie ? (count === 1 ? 'movie' : 'movies') : 'series';
    return `${count} ${label}`;
  }

  retry(): void {
    void this.facade.refresh();
  }
}
