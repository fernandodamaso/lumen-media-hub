import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  effect,
  ElementRef,
  inject,
  input,
  signal,
} from '@angular/core';
import { LucideChevronLeft, LucideChevronRight, LucidePlay } from '@lucide/angular';
import { MmProgress } from '@app/ui';
import {
  DEFAULT_LIBRARY_ART,
  JELLYFIN_LINK_BASES,
  resolveJellyfinItemLink,
} from '../library.models';
import { WatchNextItem } from '../watch-next.models';
import { resolveWatchNextPageSize } from './watch-next-grid.page-size';

const DEFAULT_PAGE_SIZE = 5;

@Component({
  selector: 'mm-watch-next-grid',
  imports: [LucideChevronLeft, LucideChevronRight, LucidePlay, MmProgress],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './watch-next-grid.html',
  styleUrls: ['./watch-next-grid.scss', '../library-poster-grid/library-poster-grid.scss'],
})
export class WatchNextGrid {
  private readonly jellyfinBases = inject(JELLYFIN_LINK_BASES);
  private readonly host = inject(ElementRef<HTMLElement>);
  private readonly destroyRef = inject(DestroyRef);

  readonly items = input.required<WatchNextItem[]>();
  readonly compact = input(true);
  readonly failedArt = signal(new Set<string>());
  readonly page = signal(0);
  readonly pageSize = signal(DEFAULT_PAGE_SIZE);

  readonly canCarousel = computed(
    () => this.compact() && this.items().length > this.pageSize(),
  );

  readonly pageCount = computed(() =>
    Math.max(1, Math.ceil(this.items().length / this.pageSize())),
  );

  readonly visibleItems = computed(() => {
    const all = this.items();
    const size = this.pageSize();
    if (!this.compact()) return all;
    if (!this.canCarousel()) return all.slice(0, size);
    const start = this.page() * size;
    return all.slice(start, start + size);
  });

  constructor() {
    afterNextRender(() => {
      const el = this.host.nativeElement as HTMLElement;
      const syncPageSize = (width: number) => {
        this.pageSize.set(resolveWatchNextPageSize(width));
      };
      syncPageSize(el.getBoundingClientRect().width);

      const observer = new ResizeObserver((entries) => {
        const width = entries[0]?.contentRect.width ?? el.getBoundingClientRect().width;
        syncPageSize(width);
      });
      observer.observe(el);
      this.destroyRef.onDestroy(() => {
        observer.disconnect();
      });
    });

    effect(() => {
      this.items();
      this.page.set(0);
      this.failedArt.set(new Set());
    });

    effect(() => {
      const maxPage = this.pageCount() - 1;
      if (this.page() > maxPage) {
        this.page.set(Math.max(0, maxPage));
      }
    });
  }

  prevPage(): void {
    this.page.update((page) => Math.max(0, page - 1));
  }

  nextPage(): void {
    this.page.update((page) => Math.min(this.pageCount() - 1, page + 1));
  }

  posterImageSrc(item: WatchNextItem): string | null {
    if (item.artworkState !== 'ok' || this.failedArt().has(item.id)) return null;
    const art = item.art.trim();
    const urlMatch = /^url\(["']?([^"')]+)["']?\)/.exec(art);
    if (urlMatch?.[1]) return urlMatch[1];
    if (art.startsWith('http://') || art.startsWith('https://')) return art;
    return null;
  }

  artStyle(item: WatchNextItem): string {
    if (this.posterImageSrc(item)) return 'transparent';
    if (item.artworkState !== 'ok' || this.failedArt().has(item.id)) {
      return DEFAULT_LIBRARY_ART;
    }
    return item.art || DEFAULT_LIBRARY_ART;
  }

  onArtError(item: WatchNextItem): void {
    this.failedArt.update((current) => {
      const next = new Set(current);
      next.add(item.id);
      return next;
    });
  }

  playHref(item: WatchNextItem): string | null {
    return item.href ?? resolveJellyfinItemLink(item, this.jellyfinBases);
  }

  progressLabel(item: WatchNextItem): string {
    return `Watched progress for ${item.title}`;
  }

  showProgress(item: WatchNextItem): boolean {
    return item.progressPercent > 0;
  }
}
