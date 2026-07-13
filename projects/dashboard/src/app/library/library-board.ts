import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { MmButton, MmPoster, MmStateCard } from 'media-ui';
import { LibraryItemKind } from '../downloads/media-stack-api';
import { LIBRARY_KIND_LABEL, libraryEmptyMessage } from './library-format';
import { LibraryFacade } from './library.facade';

@Component({
  standalone: true,
  selector: 'mm-library-board',
  imports: [MmButton, MmPoster, MmStateCard],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="library" aria-labelledby="library-heading">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Collection</p>
          <h2 id="library-heading">Library</h2>
          <p class="section-copy">Browse demo movies and series with stable poster fallbacks.</p>
        </div>
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
        <mm-state-card icon="◌" title="Loading library" message="Fetching the demo catalog…" />
      } @else if (facade.status() === 'error') {
        <mm-state-card icon="!" title="Library unavailable" [message]="facade.error()" tone="danger">
          <mm-button label="Try again" (click)="retry()" />
        </mm-state-card>
      } @else if (facade.status() === 'empty') {
        <mm-state-card icon="∅" title="Nothing here" [message]="emptyMessage()" />
      } @else {
        <div class="poster-grid" aria-live="polite">
          @for (item of facade.items(); track item.id) {
            <article
              class="poster-card"
              [class.poster-card--open]="openedId() === item.id"
              [attr.data-artwork]="item.artworkState"
              tabindex="0"
              (focusin)="openCard(item.id)"
              (focusout)="onCardFocusOut($event, item.id)"
              (mouseenter)="openCard(item.id)"
              (mouseleave)="closeCard(item.id)"
            >
              <mm-poster [title]="item.title" [meta]="item.meta" [art]="item.art" />
              <div class="poster-card__disclosure">
                @if (item.overview) {
                  <p class="poster-card__overview">{{ item.overview }}</p>
                }
                @if (item.href) {
                  <a class="poster-card__link" [href]="item.href" target="_blank" rel="noreferrer">
                    Open in Jellyfin
                  </a>
                }
              </div>
            </article>
          }
        </div>
      }
    </section>
  `,
  styles: `
    :host { display: block; }
    .library { margin-top: 52px; }
    .section-heading {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
      flex-wrap: wrap;
    }
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
    }
    .switcher__tab--active {
      background: var(--mm-component-muted-bg);
      color: var(--mm-component-text-primary);
    }
    .switcher__count {
      color: var(--mm-component-text-muted);
      font-variant-numeric: tabular-nums;
    }
    .poster-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 18px;
    }
    .poster-card {
      display: grid;
      gap: 0;
      outline: none;
    }
    .poster-card :is(mm-poster) {
      display: block;
      width: 100%;
    }
    .poster-card__disclosure {
      display: grid;
      gap: 8px;
      max-height: 0;
      opacity: 0;
      overflow: hidden;
      padding: 0 12px;
      border: 1px solid transparent;
      border-radius: 0 0 var(--mm-radius-md) var(--mm-radius-md);
      background: var(--mm-component-card-bg);
      transition: max-height .2s ease, opacity .18s ease, padding .18s ease;
      pointer-events: none;
    }
    .poster-card:hover .poster-card__disclosure,
    .poster-card:focus-within .poster-card__disclosure,
    .poster-card--open .poster-card__disclosure {
      max-height: 140px;
      opacity: 1;
      padding: 10px 12px 12px;
      border-color: var(--mm-component-border);
      border-top-color: transparent;
      pointer-events: auto;
    }
    .poster-card__overview {
      margin: 0;
      color: var(--mm-component-text-secondary);
      font-size: 12px;
      line-height: 1.45;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .poster-card__link {
      color: var(--mm-component-accent);
      font-size: 12px;
      font-weight: 700;
      text-decoration: none;
    }
    .poster-card__link:hover,
    .poster-card__link:focus-visible {
      text-decoration: underline;
    }
    .poster-card:focus-visible {
      box-shadow: 0 0 0 2px var(--mm-component-accent);
      border-radius: var(--mm-radius-md);
    }
  `,
})
export class LibraryBoard {
  readonly facade = inject(LibraryFacade);
  readonly openedId = signal<string | null>(null);

  kindLabel(kind: LibraryItemKind): string {
    return LIBRARY_KIND_LABEL[kind];
  }

  openCard(id: string): void {
    this.openedId.set(id);
  }

  closeCard(id: string): void {
    if (this.openedId() === id) this.openedId.set(null);
  }

  onCardFocusOut(event: FocusEvent, id: string): void {
    const next = event.relatedTarget as Node | null;
    if (next && (event.currentTarget as Node).contains(next)) return;
    this.closeCard(id);
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
