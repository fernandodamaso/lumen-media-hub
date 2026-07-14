import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MmButton, MmCard, MmPoster, MmStateCard } from 'media-ui';
import { LibraryItemKind } from '../downloads/media-stack-api';
import { LIBRARY_KIND_LABEL, libraryEmptyMessage } from './library-format';
import { LibraryFacade } from './library.facade';

@Component({
  standalone: true,
  selector: 'mm-library-board',
  imports: [MmButton, MmCard, MmPoster, MmStateCard],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mm-card class="library" labelledBy="library-heading">
        <div mm-card-header>
          <p class="eyebrow">Collection</p>
          <h2 id="library-heading">Library</h2>
          <p class="section-copy">Browse movies and series in the local library.</p>
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
        @if (facade.viewAllHref(); as href) { <a class="view-all" [href]="href" target="_blank" rel="noreferrer">View all ↗</a> }
        </div>

      @if (facade.status() === 'loading') {
        <mm-state-card kind="loading" title="Loading library" message="Fetching the demo catalog…" />
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
    </mm-card>
  `,
  styles: `
    :host { display: block; }
    .header-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    h2 { margin: 0; color: var(--mm-component-text-primary); font-size: 24px; }
    .section-copy { margin-top: 6px; color: var(--mm-component-text-secondary); font-size: 14px; }
    .switcher {
      display: inline-flex;
      gap: 6px;
      padding: 4px;
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-md);
      background: var(--mm-component-card-bg);
    }
    .switcher__tab {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 0;
      border-radius: var(--mm-radius-sm);
      padding: 8px 12px;
      background: transparent;
      color: var(--mm-component-text-secondary);
      cursor: pointer;
      font: 700 13px/1 var(--mm-font-body);
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
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }
    .poster-card {
      display: block;
      outline: none;
      color: inherit;
      text-decoration: none;
    }
    .poster-card :is(mm-poster) {
      display: block;
      width: 100%;
      max-width: none;
    }
    .poster-card:nth-child(n+9) { display: none; }
    .view-all { color: var(--mm-component-accent); font-size: 13px; font-weight: 700; text-decoration: none; }
    .poster-card:focus-visible {
      box-shadow: 0 0 0 2px var(--mm-component-accent);
      border-radius: var(--mm-radius-md);
    }
    @container (min-width: 960px) {
      .poster-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); }
      .poster-card { display: block; }
      .poster-card:nth-child(n+13) { display: none; }
    }
    @container (max-width: 639px) {
      .poster-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .poster-card:nth-child(n+5) { display: none; }
    }
  `,
})
export class LibraryBoard {
  readonly facade = inject(LibraryFacade);

  kindLabel(kind: LibraryItemKind): string {
    return LIBRARY_KIND_LABEL[kind];
  }

  setKind(kind: LibraryItemKind): void {
    this.facade.setKind(kind);
  }

  emptyMessage(): string {
    return libraryEmptyMessage(this.facade.kind());
  }

  retry(): void {
    void this.facade.refresh();
  }
}
