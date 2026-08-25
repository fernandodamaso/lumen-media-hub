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
import { MmIconButton } from '@app/ui';
import {
  JELLYFIN_LINK_BASES,
  LibraryItem,
  LibraryItemKind,
  resolveJellyfinItemLink,
} from '../library.models';
import { LibraryPosterCard } from '../library-poster-card/library-poster-card';
import { LibraryManagerLinksFacade } from '../library-manager-links.facade';

const COMPACT_PAGE_SIZE = 5;

@Component({
  selector: 'mm-library-poster-grid',
  imports: [MmIconButton, LibraryPosterCard, LucideChevronLeft, LucideChevronRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library-poster-grid.html',
  styleUrl: './library-poster-grid.scss',
})
export class LibraryPosterGrid {
  private readonly jellyfinBases = inject(JELLYFIN_LINK_BASES);
  private readonly managerLinks = inject(LibraryManagerLinksFacade);

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

  playHref(item: LibraryItem): string | null {
    return item.href ?? resolveJellyfinItemLink(item, this.jellyfinBases);
  }

  detailHref(item: LibraryItem): string | null {
    return this.managerLinks.resolveHref(item) ?? this.playHref(item);
  }

  kindLabel(kind: LibraryItemKind): string {
    return kind === 'movie' ? 'Movie' : 'Series';
  }
}
