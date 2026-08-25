import { inject, Injectable, signal } from '@angular/core';
import { ArrLibrary, CALENDAR_LINK_BASES } from '../calendar/calendar.models';
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

  resolveHref(
    item: Pick<LibraryItem, 'title' | 'kind'> & Partial<Pick<LibraryItem, 'meta'>>,
  ): string | null {
    const titleKey = item.title.trim().toLowerCase();
    if (!titleKey) return null;

    const slugs = item.kind === 'movie' ? this.library().movies : this.library().series;
    const year = item.meta?.match(/\b(?:18|19|20)\d{2}\b/)?.[0];
    const slug = (year ? slugs[`${titleKey}::${year}`] : undefined) ?? slugs[titleKey];
    if (!slug) return null;

    const rawBase = item.kind === 'movie' ? this.linkBases.radarrBase : this.linkBases.sonarrBase;
    const base = (rawBase ?? '').replace(/\/$/, '');
    if (!base) return null;
    const segment = item.kind === 'movie' ? 'movie' : 'series';
    return `${base}/${segment}/${slug}`;
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
