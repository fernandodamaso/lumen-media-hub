import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { LucideLibrary } from '@lucide/angular';
import { MmButton, MmCard, MmPoster, MmSkeleton, MmStateCard } from '@app/ui';
import { LibraryItemKind } from './library.models';
import { LIBRARY_KIND_LABEL, libraryEmptyMessage } from './library-format';
import { LibraryFacade } from './library.facade';

@Component({
  selector: 'mm-library-board',
  imports: [MmButton, MmCard, MmPoster, MmSkeleton, MmStateCard, LucideLibrary],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library-board.html',
  styleUrl: './library-board.scss',
})
export class LibraryBoard {
  readonly facade = inject(LibraryFacade);
  readonly posterSkeletons = [0, 1, 2, 3, 4, 5];

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
