import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MmButton, MmStateCard, MmStatus } from '@app/ui';
import { LibraryItemKind } from '../library.models';
import { LibraryItemsFacade } from '../library-items.facade';
import { LibraryPosterGrid } from '../library-poster-grid/library-poster-grid';

@Component({
  selector: 'mm-library-page',
  imports: [LibraryPosterGrid, MmButton, MmStateCard, MmStatus],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library-page.html',
  styleUrl: './library-page.scss',
})
export class LibraryPage {
  readonly facade = inject(LibraryItemsFacade);
  readonly filter = signal<LibraryItemKind | 'all'>('all');

  readonly filteredItems = computed(() => {
    const filter = this.filter();
    const items = this.facade.items();
    return filter === 'all' ? items : items.filter((item) => item.kind === filter);
  });

  setFilter(filter: LibraryItemKind | 'all'): void {
    this.filter.set(filter);
  }

  retry(): void {
    void this.facade.refresh({ initial: true });
  }
}
