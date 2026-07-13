import { InjectionToken } from '@angular/core';

export type TorrentState = 'downloading' | 'seeding' | 'paused' | 'queued' | 'checking' | 'error';

/** Raw qBittorrent-shaped data stays behind this boundary. */
export interface MediaStackTorrentDto {
  hash: string;
  name: string;
  state: string;
  progress: number;
  size: number;
  downloaded: number;
  dlspeed: number;
  upspeed: number;
  eta: number;
  category?: string;
}

export type CalendarMediaKind = 'episode' | 'movie';
export type CalendarEventStatus = 'available' | 'pending';

/** Raw Sonarr/Radarr calendar payload stays behind this boundary. */
export interface MediaStackCalendarEventDto {
  title: string;
  additional: string;
  date: string;
  airDate?: string;
  hasFile?: boolean;
  kind?: CalendarMediaKind;
  seriesId?: number;
}

export interface MediaStackArrLibraryDto {
  ok: boolean;
  series: Record<string, string>;
  movies: Record<string, string>;
  error?: string;
}

export type DiscoverFeedback = 'liked' | 'disliked' | 'watched' | 'skipped';
export type DiscoverMediaType = 'movie' | 'tv';
export type DiscoverSourceTab = 'hermes' | 'jellyseerr' | 'trakt';
export type JellyseerrDiscoverKind = 'trending' | 'movies' | 'tv';
export type TraktDiscoverType = 'movies' | 'shows';

export interface MediaStackDiscoverItemDto {
  id: string;
  source: string;
  type: DiscoverMediaType;
  title: string;
  year?: number | null;
  tmdb_id: number;
  reason?: string;
  active: boolean;
  feedback: DiscoverFeedback | null;
  feedback_at: string | null;
  request_state: 'requested' | null;
  requested_at: string | null;
  jellyseerr_request_id: number | null;
  in_library?: boolean;
  jellyfin_id?: string | null;
  poster_path?: string | null;
  poster_url?: string | null;
  added_at: string;
  notes?: string;
  rating?: number | null;
}

export interface MediaStackExternalDiscoverItemDto {
  id?: string;
  source?: string;
  type: DiscoverMediaType;
  title: string;
  year?: number | null;
  tmdb_id: number;
  overview?: string;
  poster_url?: string | null;
  rating?: number | null;
}

export interface MediaStackHermesDiscoverDto {
  ok: boolean;
  items: MediaStackDiscoverItemDto[];
  pending_request_sync?: { id: string; jellyseerr_request_id: number }[];
  generation_request?: { requested_at: string; status: 'pending' } | null;
  error?: string;
}

export interface MediaStackExternalDiscoverDto {
  ok: boolean;
  items: MediaStackExternalDiscoverItemDto[];
  error?: string;
}

export interface MediaStackDiscoverActionDto {
  ok: boolean;
  error?: string;
  message?: string;
  partial_success?: boolean;
  jellyseerr_request_id?: number | null;
  dashboard_state_persisted?: boolean;
  reconciliation_queued?: boolean;
  queued?: boolean;
  already_pending?: boolean;
  requested_at?: string;
}

export interface MediaStackDiscoverRequestPayload {
  mediaType: DiscoverMediaType;
  mediaId: number;
  hermesId?: string;
  is4k?: boolean;
}

export interface MediaStackApi {
  listTorrents(): Promise<MediaStackTorrentDto[]>;
  pauseAll(): Promise<void>;
  resumeAll(): Promise<void>;
  listCalendarEvents(): Promise<MediaStackCalendarEventDto[]>;
  getArrLibrary(): Promise<MediaStackArrLibraryDto>;
  listHermesRecommendations(): Promise<MediaStackHermesDiscoverDto>;
  submitHermesFeedback(id: string, feedback: DiscoverFeedback, notes?: string): Promise<MediaStackDiscoverActionDto>;
  requestHermesMore(): Promise<MediaStackDiscoverActionDto>;
  listJellyseerrDiscover(kind: JellyseerrDiscoverKind): Promise<MediaStackExternalDiscoverDto>;
  listTraktDiscover(type: TraktDiscoverType): Promise<MediaStackExternalDiscoverDto>;
  requestMedia(payload: MediaStackDiscoverRequestPayload): Promise<MediaStackDiscoverActionDto>;
}

export const MEDIA_STACK_API = new InjectionToken<MediaStackApi>('MEDIA_STACK_API');

export interface CalendarEvent {
  id: string;
  time: string;
  kind: CalendarMediaKind;
  title: string;
  subtitle: string;
  status: CalendarEventStatus;
  airDate: string;
}

export interface CalendarLinkBases {
  sonarrBase?: string;
  radarrBase?: string;
}

export const DEFAULT_CALENDAR_LINK_BASES: Required<CalendarLinkBases> = {
  sonarrBase: 'http://localhost:8989',
  radarrBase: 'http://localhost:7878',
};

export const CALENDAR_LINK_BASES = new InjectionToken<CalendarLinkBases>('CALENDAR_LINK_BASES', {
  providedIn: 'root',
  factory: () => ({ ...DEFAULT_CALENDAR_LINK_BASES }),
});

export const compareCalendarEvents = (left: CalendarEvent, right: CalendarEvent): number => {
  const leftKey = left.airDate || '\uffff';
  const rightKey = right.airDate || '\uffff';
  const byAirDate = leftKey.localeCompare(rightKey);
  if (byAirDate !== 0) return byAirDate;
  const byTime = left.time.localeCompare(right.time);
  if (byTime !== 0) return byTime;
  return left.title.localeCompare(right.title);
};

export interface DownloadTorrent {
  id: string;
  name: string;
  state: TorrentState;
  progress: number;
  size: number;
  downloaded: number;
  downloadRate: number;
  uploadRate: number;
  eta: number;
  category: string;
}

export interface DownloadSummary {
  active: number;
  total: number;
  downloaded: number;
  size: number;
  downloadRate: number;
  uploadRate: number;
}

export const normalizeTorrent = (torrent: MediaStackTorrentDto): DownloadTorrent => ({
  id: torrent.hash,
  name: torrent.name,
  state: normalizeState(torrent.state),
  progress: clamp(torrent.progress * 100),
  size: Math.max(0, torrent.size),
  downloaded: Math.max(0, torrent.downloaded),
  downloadRate: Math.max(0, torrent.dlspeed),
  uploadRate: Math.max(0, torrent.upspeed),
  eta: Math.max(0, torrent.eta),
  category: torrent.category ?? 'Uncategorized',
});

export const summarizeDownloads = (torrents: DownloadTorrent[]): DownloadSummary => ({
  active: torrents.filter((torrent) => torrent.state === 'downloading').length,
  total: torrents.length,
  downloaded: torrents.reduce((sum, torrent) => sum + torrent.downloaded, 0),
  size: torrents.reduce((sum, torrent) => sum + torrent.size, 0),
  downloadRate: torrents.reduce((sum, torrent) => sum + torrent.downloadRate, 0),
  uploadRate: torrents.reduce((sum, torrent) => sum + torrent.uploadRate, 0),
});

export const normalizeCalendarEvent = (event: MediaStackCalendarEventDto): CalendarEvent => {
  const airDate = event.airDate ?? '';
  const kind = event.kind ?? (looksLikeEpisode(event.additional) ? 'episode' : 'movie');
  return {
    id: `${event.title}-${event.additional}-${airDate || event.date}`,
    time: event.date,
    kind,
    title: event.title,
    subtitle: event.additional,
    status: event.hasFile ? 'available' : 'pending',
    airDate,
  };
};

export const resolveCalendarLink = (
  title: string | null | undefined,
  library: Pick<MediaStackArrLibraryDto, 'series' | 'movies'>,
  bases: CalendarLinkBases = {},
  kind?: CalendarMediaKind,
): string | null => {
  if (!title) return null;
  const key = title.trim().toLowerCase();
  const sonarrBase = (bases.sonarrBase ?? DEFAULT_CALENDAR_LINK_BASES.sonarrBase).replace(/\/$/, '');
  const radarrBase = (bases.radarrBase ?? DEFAULT_CALENDAR_LINK_BASES.radarrBase).replace(/\/$/, '');
  const seriesHref = library.series?.[key] ? `${sonarrBase}/series/${library.series[key]}` : null;
  const movieHref = library.movies?.[key] ? `${radarrBase}/movie/${library.movies[key]}` : null;
  if (kind === 'movie') return movieHref ?? seriesHref;
  if (kind === 'episode') return seriesHref ?? movieHref;
  return seriesHref ?? movieHref;
};

function clamp(value: number): number {
  return Math.round(Math.min(100, Math.max(0, value)) * 10) / 10;
}

function normalizeState(state: string): TorrentState {
  const normalized = state.toLowerCase();
  if (normalized.includes('paused')) return 'paused';
  if (normalized.includes('error')) return 'error';
  if (normalized.includes('check')) return 'checking';
  if (normalized.includes('queued')) return 'queued';
  if (normalized === 'downloading' || normalized === 'forceddl') return 'downloading';
  if (normalized.includes('up') || normalized === 'seeding') return 'seeding';
  return 'queued';
}

function looksLikeEpisode(additional: string): boolean {
  return /^S\d+\s*E\d+/i.test(additional.trim());
}
