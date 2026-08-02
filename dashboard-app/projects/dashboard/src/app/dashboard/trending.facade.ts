import { DestroyRef, inject, Injectable, signal } from '@angular/core';
import { ExternalDiscoverItem } from '../discover/discover.models';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';

export interface TrendingItem {
  id: string;
  title: string;
  year: number | null;
  type: 'movie' | 'tv';
  posterUrl: string | null;
  rating: number | null;
  /** Direct Trakt page URL for the title. */
  href: string;
  /** 1-based rank in the merged interleaved feed. */
  rank: number;
}

export type TrendingStatus = 'loading' | 'ready' | 'empty' | 'error';

const LOAD_ERROR = 'Trending titles are temporarily unavailable. Try again.';
const REFRESH_ERROR = 'Could not refresh trending titles. Showing last loaded results.';
const TRENDING_LIMIT = 12;

/**
 * Slim read-only trending feed for the dashboard rail.
 * Deliberately NOT DiscoverFacade: that facade is page-scoped and owns
 * tabs/filters/Hermes polling the rail must not start.
 */
@Injectable({ providedIn: 'root' })
export class TrendingFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<TrendingStatus>('loading');
  private readonly _items = signal<TrendingItem[]>([]);
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private requestId = 0;

  readonly status = this._status.asReadonly();
  readonly items = this._items.asReadonly();
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.requestId++;
    });
    void this.refresh({ initial: true });
  }

  async refresh(options: { initial?: boolean; signal?: AbortSignal } = {}): Promise<void> {
    const initial =
      options.initial === true || this._status() === 'loading' || this._status() === 'error';
    this._refreshing.set(true);
    const requestId = ++this.requestId;
    try {
      const [shows, movies] = await Promise.all([
        this.api.listTraktDiscover('shows', options.signal),
        this.api.listTraktDiscover('movies', options.signal),
      ]);
      if (requestId !== this.requestId) return;
      if (!shows.ok && !movies.ok) {
        throw new Error(shows.error ?? movies.error ?? LOAD_ERROR);
      }
      const items = mergeTrending(
        shows.ok && shows.availability !== 'disabled' ? shows.items : [],
        movies.ok && movies.availability !== 'disabled' ? movies.items : [],
      );
      this._items.set(items);
      this._error.set('');
      this._status.set(items.length ? 'ready' : 'empty');
    } catch {
      if (requestId !== this.requestId) return;
      if (options.signal?.aborted) return;
      if (!initial && (this._status() === 'ready' || this._status() === 'empty')) {
        this._error.set(REFRESH_ERROR);
      } else {
        this._status.set('error');
        this._error.set(LOAD_ERROR);
        if (initial) this._items.set([]);
      }
    } finally {
      if (requestId === this.requestId) this._refreshing.set(false);
    }
  }
}

/** Interleave shows/movies by per-list rank, then number the merged feed. */
function mergeTrending(
  shows: readonly ExternalDiscoverItem[],
  movies: readonly ExternalDiscoverItem[],
  limit = TRENDING_LIMIT,
): TrendingItem[] {
  const merged: TrendingItem[] = [];
  const max = Math.max(shows.length, movies.length);
  for (let i = 0; i < max; i++) {
    if (i < shows.length) merged.push(toTrendingItem(shows[i], 'tv'));
    if (i < movies.length) merged.push(toTrendingItem(movies[i], 'movie'));
  }
  return merged.slice(0, limit).map((item, index) => ({ ...item, rank: index + 1 }));
}

function toTrendingItem(item: ExternalDiscoverItem, type: 'movie' | 'tv'): TrendingItem {
  return {
    id: `trakt-${type}-${item.tmdb_id}`,
    title: item.title,
    year: item.year ?? null,
    type,
    posterUrl: item.poster_url ?? null,
    rating: item.rating ?? null,
    href: resolveTraktHref(item, type),
    rank: 0,
  };
}

function resolveTraktHref(item: ExternalDiscoverItem, type: 'movie' | 'tv'): string {
  const slug = item.trakt_slug?.trim();
  if (slug) {
    const path = type === 'movie' ? 'movies' : 'shows';
    return `https://trakt.tv/${path}/${encodeURIComponent(slug)}`;
  }
  const idType = type === 'movie' ? 'movie' : 'show';
  return `https://trakt.tv/search/tmdb/${item.tmdb_id}?id_type=${idType}`;
}
