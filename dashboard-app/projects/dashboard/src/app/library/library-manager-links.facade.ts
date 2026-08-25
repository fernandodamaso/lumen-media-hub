import { inject, Injectable, signal } from '@angular/core';
import {
  ArrLibrary,
  CALENDAR_LINK_BASES,
  resolveCalendarLink,
} from '../calendar/calendar.models';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { LibraryItem } from './library.models';

const EMPTY_LIBRARY: Pick<ArrLibrary, 'series' | 'movies'> = {
  series: {},
  movies: {},
};

@Injectable()
export class LibraryManagerLinksFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly linkBases = inject(CALENDAR_LINK_BASES);
  private readonly library = signal<Pick<ArrLibrary, 'series' | 'movies'>>(EMPTY_LIBRARY);

  constructor() {
    void this.refresh();
  }

  resolveHref(item: Pick<LibraryItem, 'title' | 'kind'>): string | null {
    const library = this.library();
    return resolveCalendarLink(
      item.title,
      item.kind === 'movie'
        ? { movies: library.movies, series: {} }
        : { movies: {}, series: library.series },
      this.linkBases,
      item.kind === 'movie' ? 'movie' : 'episode',
    );
  }

  async refresh(): Promise<void> {
    try {
      const library = await this.api.getArrLibrary();
      this.library.set(library.ok ? library : EMPTY_LIBRARY);
    } catch {
      this.library.set(EMPTY_LIBRARY);
    }
  }
}
