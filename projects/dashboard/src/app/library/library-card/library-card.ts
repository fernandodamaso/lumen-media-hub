import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LucideChevronRight } from '@lucide/angular';
import { MmButton, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { LibraryItemKind } from '../library.models';
import { LibraryItemsFacade } from '../library-items.facade';
import { LibraryPosterGrid } from '../library-poster-grid/library-poster-grid';

@Component({
  selector: 'mm-library-card',
  imports: [LibraryPosterGrid, MmButton, MmSkeleton, MmStateCard, MmStatus, RouterLink, LucideChevronRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library-card.html',
  styleUrl: './library-card.scss',
})
export class LibraryCard {
  readonly facade = inject(LibraryItemsFacade);
  readonly tab = signal<LibraryItemKind>('series');
  readonly skeletons = [0, 1, 2, 3];

  readonly filteredItems = computed(() =>
    this.facade.items().filter((item) => item.kind === this.tab()).slice(0, 8),
  );

  readonly movieCount = computed(() => this.facade.movieCount());
  readonly seriesCount = computed(() => this.facade.seriesCount());

  setTab(kind: LibraryItemKind): void {
    this.tab.set(kind);
  }

  retry(): void {
    void this.facade.refresh({ initial: true });
  }
}
