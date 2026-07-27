import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LucideChevronRight } from '@lucide/angular';
import { MmButton, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { WatchNextFacade } from '../watch-next.facade';
import { WatchNextGrid } from '../watch-next-grid/watch-next-grid';

/** Segmented tab; maps to watch-next item kinds `movie` vs `episode`. */
type LibraryCardTab = 'movies' | 'series';

@Component({
  selector: 'mm-library-card',
  imports: [WatchNextGrid, MmButton, MmSkeleton, MmStateCard, MmStatus, RouterLink, LucideChevronRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library-card.html',
  styleUrl: './library-card.scss',
})
export class LibraryCard {
  readonly facade = inject(WatchNextFacade);
  readonly tab = signal<LibraryCardTab>('series');
  readonly skeletons = [0, 1, 2, 3];

  readonly filteredItems = computed(() => {
    const kind = this.tab() === 'movies' ? 'movie' : 'episode';
    return this.facade.items().filter((item) => item.kind === kind).slice(0, 8);
  });

  readonly movieCount = computed(() => this.facade.movieCount());
  readonly seriesCount = computed(() => this.facade.seriesCount());

  setTab(tab: LibraryCardTab): void {
    this.tab.set(tab);
  }

  retry(): void {
    void this.facade.refresh({ initial: true });
  }
}
