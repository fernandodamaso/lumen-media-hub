import { computed, inject, Injectable } from '@angular/core';
import {
  JellyfinLinkBases,
  JELLYFIN_LINK_BASES,
  resolveJellyfinItemLink,
} from '../../library/library.models';
import { WatchNextFacade } from '../../library/watch-next.facade';
import { WatchNextItem, WatchNextKind } from '../../library/watch-next.models';

export interface HeroTitleParts {
  head: string;
  tail: string;
}

export interface HeroView {
  id: string;
  kind: WatchNextKind;
  title: string;
  titleParts: HeroTitleParts;
  kicker: string;
  backdropUrl: string;
  meta: string[];
  overview: string;
  progressPercent: number;
  remainingLabel: string;
  playHref: string | null;
}

const TICKS_PER_MINUTE = 600_000_000;

/** Featured item = first watch-next entry with a backdrop that is playable. */
export function selectHeroCandidate(items: readonly WatchNextItem[]): WatchNextItem | null {
  return items.find((item) => item.playable && !!item.backdropUrl) ?? null;
}

/** Last word of the title gets the gold italic treatment. */
export function splitTitleEmphasis(title: string): HeroTitleParts {
  const trimmed = title.trim().replace(/\s+/g, ' ');
  const split = trimmed.lastIndexOf(' ');
  if (split <= 0) return { head: '', tail: trimmed };
  return { head: trimmed.slice(0, split), tail: trimmed.slice(split + 1) };
}

export function formatRuntimeTicks(ticks: number | null): string {
  if (!ticks || ticks <= 0) return '';
  const totalMinutes = Math.round(ticks / TICKS_PER_MINUTE);
  if (totalMinutes <= 0) return '';
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export function formatRemainingLabel(runtimeTicks: number | null, positionTicks: number | null): string {
  if (!runtimeTicks) return '';
  const remaining = runtimeTicks - (positionTicks ?? 0);
  if (remaining <= 0) return '';
  const label = formatRuntimeTicks(remaining);
  return label ? `${label} remaining` : '';
}

/** Normalizes "S02E04 · name" to the mock's "S2 E4 · name" meta form. */
function formatEpisodeCode(subtitle: string): string {
  return subtitle.replace(/S(\d+)E(\d+)/i, (_match, season: string, episode: string) => `S${Number(season)} E${Number(episode)}`);
}

export function buildHeroView(item: WatchNextItem, bases: JellyfinLinkBases = {}): HeroView {
  const meta: string[] = [];
  // Episodes present series identity; the episode code leads the meta line.
  if (item.kind === 'episode' && item.subtitle) meta.push(formatEpisodeCode(item.subtitle));
  if (item.year) meta.push(String(item.year));
  if (item.rating) meta.push(`★ ${item.rating.toFixed(1)}`);
  const runtime = formatRuntimeTicks(item.runtimeTicks);
  if (runtime) meta.push(runtime);
  if (item.genres.length) meta.push(item.genres.slice(0, 2).join(', '));

  return {
    id: item.id,
    kind: item.kind,
    title: item.title,
    titleParts: splitTitleEmphasis(item.title),
    kicker: 'Featured',
    backdropUrl: item.backdropUrl ?? '',
    meta,
    overview: item.overview ?? '',
    progressPercent: item.progressPercent,
    remainingLabel: formatRemainingLabel(item.runtimeTicks, item.positionTicks),
    playHref: resolveJellyfinItemLink({ id: item.id, playable: item.playable }, bases),
  };
}

@Injectable({ providedIn: 'root' })
export class HeroFacade {
  private readonly watchNext = inject(WatchNextFacade);
  private readonly jellyfinBases = inject(JELLYFIN_LINK_BASES);

  readonly featured = computed(() => selectHeroCandidate(this.watchNext.items()));

  /** Null when no candidate qualifies — the hero hides gracefully. */
  readonly view = computed<HeroView | null>(() => {
    const candidate = this.featured();
    return candidate ? buildHeroView(candidate, this.jellyfinBases) : null;
  });
}
