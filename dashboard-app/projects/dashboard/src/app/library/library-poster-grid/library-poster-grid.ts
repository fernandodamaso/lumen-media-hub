import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { LucideChevronLeft, LucideChevronRight } from '@lucide/angular';
import { MmIconButton, MmPoster } from '@app/ui';
import {
  DEFAULT_LIBRARY_ART,
  JELLYFIN_LINK_BASES,
  LibraryItem,
  LibraryItemKind,
  resolveJellyfinItemLink,
} from '../library.models';

const COMPACT_PAGE_SIZE = 5;

@Component({
  selector: 'mm-library-poster-grid',
  imports: [MmIconButton, MmPoster, LucideChevronLeft, LucideChevronRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library-poster-grid.html',
  styleUrl: './library-poster-grid.scss',
})
export class LibraryPosterGrid {
  private readonly jellyfinBases = inject(JELLYFIN_LINK_BASES);

  readonly items = input.required<LibraryItem[]>();
  readonly compact = input(false);
  readonly page = signal(0);
  readonly artNonce = signal(0);

  readonly canCarousel = computed(
    () => this.compact() && this.items().length > COMPACT_PAGE_SIZE,
  );

  readonly pageCount = computed(() =>
    Math.max(1, Math.ceil(this.items().length / COMPACT_PAGE_SIZE)),
  );

  readonly visibleItems = computed(() => {
    const all = this.items();
    if (!this.compact()) return all;
    if (!this.canCarousel()) return all.slice(0, COMPACT_PAGE_SIZE);
    const start = this.page() * COMPACT_PAGE_SIZE;
    return all.slice(start, start + COMPACT_PAGE_SIZE);
  });

  constructor() {
    effect(() => {
      this.items();
      this.page.set(0);
      this.artNonce.update((n) => n + 1);
    });
  }

  prevPage(): void {
    this.page.update((page) => Math.max(0, page - 1));
  }

  nextPage(): void {
    this.page.update((page) => Math.min(this.pageCount() - 1, page + 1));
  }

  posterImageSrc(item: LibraryItem): string | null {
    if (item.artworkState !== 'ok') return null;
    const art = item.art.trim();
    const urlMatch = /^url\(["']?([^"')]+)["']?\)/.exec(art);
    if (urlMatch?.[1]) return urlMatch[1];
    if (art.startsWith('http://') || art.startsWith('https://')) return art;
    return null;
  }

  posterFallbackArt(item: LibraryItem): string {
    if (item.artworkState !== 'ok' || this.posterImageSrc(item)) return DEFAULT_LIBRARY_ART;
    return item.art || DEFAULT_LIBRARY_ART;
  }

  playHref(item: LibraryItem): string | null {
    return item.href ?? resolveJellyfinItemLink(item, this.jellyfinBases);
  }

  kindLabel(kind: LibraryItemKind): string {
    return kind === 'movie' ? 'Movie' : 'Series';
  }
}
