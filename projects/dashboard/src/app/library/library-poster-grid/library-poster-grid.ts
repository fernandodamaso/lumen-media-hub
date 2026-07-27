import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { LucideChevronLeft, LucideChevronRight, LucidePlay } from '@lucide/angular';
import { MmTooltip } from '@app/ui';
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
  imports: [LucideChevronLeft, LucideChevronRight, LucidePlay, MmTooltip],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library-poster-grid.html',
  styleUrl: './library-poster-grid.scss',
})
export class LibraryPosterGrid {
  private readonly jellyfinBases = inject(JELLYFIN_LINK_BASES);

  readonly items = input.required<LibraryItem[]>();
  readonly compact = input(false);
  readonly failedArt = signal(new Set<string>());
  readonly page = signal(0);

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
      this.failedArt.set(new Set());
    });
  }

  prevPage(): void {
    this.page.update((page) => Math.max(0, page - 1));
  }

  nextPage(): void {
    this.page.update((page) => Math.min(this.pageCount() - 1, page + 1));
  }

  posterImageSrc(item: LibraryItem): string | null {
    if (item.artworkState !== 'ok' || this.failedArt().has(item.id)) return null;
    const art = item.art.trim();
    const urlMatch = /^url\(["']?([^"')]+)["']?\)/.exec(art);
    if (urlMatch?.[1]) return urlMatch[1];
    if (art.startsWith('http://') || art.startsWith('https://')) return art;
    return null;
  }

  artStyle(item: LibraryItem): string {
    if (this.posterImageSrc(item)) return 'transparent';
    if (item.artworkState !== 'ok' || this.failedArt().has(item.id)) {
      return DEFAULT_LIBRARY_ART;
    }
    return item.art || DEFAULT_LIBRARY_ART;
  }

  onArtError(item: LibraryItem): void {
    this.failedArt.update((current) => {
      const next = new Set(current);
      next.add(item.id);
      return next;
    });
  }

  playHref(item: LibraryItem): string | null {
    return item.href ?? resolveJellyfinItemLink(item, this.jellyfinBases);
  }

  kindLabel(kind: LibraryItemKind): string {
    return kind === 'movie' ? 'Movie' : 'Series';
  }
}
