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


/** Raw cron-log run from GET /cron/logs. Status values stay contract-shaped. */
export interface MediaStackCronLogRunDto {
  timestamp?: string;
  exitCode?: number;
  status?: string;
  applied?: number;
  evaluated?: number;
  skipped?: number;
  fatal?: string | null;
  detail?: string;
  highlights?: string[];
}

/** Per-job cron log entry from GET /cron/logs. */
export interface MediaStackCronLogEntryDto {
  id: string;
  title: string;
  file: string;
  format: string;
  schedule: string;
  description?: string;
  actions?: string[];
  exists: boolean;
  size?: number;
  mtime?: string | null;
  summary?: string;
  lastStatus?: string;
  runs?: MediaStackCronLogRunDto[];
}

/** Envelope returned by GET /cron/logs. */
export interface MediaStackCronLogsDto {
  ok: boolean;
  generatedAt?: string;
  tmpDir?: string;
  logs: MediaStackCronLogEntryDto[];
  note?: string;
  error?: string;
}

export type LibraryItemKind = 'movie' | 'series';
export type LibraryArtworkState = 'ok' | 'missing' | 'failed';

/** Raw Jellyfin-shaped browse payload stays behind this boundary. */
export interface MediaStackLibraryItemDto {
  id: string;
  title: string;
  kind: LibraryItemKind | string;
  year?: number;
  overview?: string;
  posterUrl?: string;
  artworkState?: LibraryArtworkState;
  playable?: boolean;
}

export interface LibraryItem {
  id: string;
  title: string;
  kind: LibraryItemKind;
  meta: string;
  art: string;
  overview: string;
  href: string | null;
  artworkState: LibraryArtworkState;
  playable: boolean;
}

export interface JellyfinLinkBases {
  jellyfinBase?: string;
}

/** Disabled by default; local Demo/live inject bases from environment. */
export const DEFAULT_JELLYFIN_LINK_BASES: Required<JellyfinLinkBases> = {
  jellyfinBase: '',
};

/** Explicit no-op bases for static/Pages builds and tests. */
export const DISABLED_JELLYFIN_LINK_BASES: Required<JellyfinLinkBases> = {
  jellyfinBase: '',
};

export const JELLYFIN_LINK_BASES = new InjectionToken<JellyfinLinkBases>('JELLYFIN_LINK_BASES', {
  providedIn: 'root',
  factory: () => ({ ...DEFAULT_JELLYFIN_LINK_BASES }),
});

export const DEFAULT_LIBRARY_ART =
  'linear-gradient(145deg, var(--mm-component-accent), var(--mm-component-card-bg) 65%)';


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
  listLibraryItems(filter?: { kind?: LibraryItemKind }): Promise<MediaStackLibraryItemDto[]>;
  getAutomationSummary(): Promise<MediaStackAutomationSummaryDto>;
  listCronLogs(): Promise<MediaStackCronLogsDto>;
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

/** Disabled by default; local Demo/live inject bases from environment. */
export const DEFAULT_CALENDAR_LINK_BASES: Required<CalendarLinkBases> = {
  sonarrBase: '',
  radarrBase: '',
};

/** Explicit no-op bases for static/Pages builds and tests. */
export const DISABLED_CALENDAR_LINK_BASES: Required<CalendarLinkBases> = {
  sonarrBase: '',
  radarrBase: '',
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
  // Empty bases must not emit relative /series/... or /movie/... URLs.
  const seriesHref =
    sonarrBase && library.series?.[key] ? `${sonarrBase}/series/${library.series[key]}` : null;
  const movieHref =
    radarrBase && library.movies?.[key] ? `${radarrBase}/movie/${library.movies[key]}` : null;
  if (kind === 'movie') return movieHref ?? seriesHref;
  if (kind === 'episode') return seriesHref ?? movieHref;
  return seriesHref ?? movieHref;
};

export type CronRunTriage = 'actionable' | 'quiet';
export type CronHealthKind = 'empty' | 'allClear' | 'mixed';

/** Flattened triage row for Reports. Contract `status` is preserved as-is. */
export interface CronRun {
  id: string;
  jobId: string;
  jobTitle: string;
  status: string;
  triage: CronRunTriage;
  timestamp: string;
  detail: string;
  fatal: string | null;
  applied: number | null;
  exitCode: number | null;
}

export interface CronHealthSummary {
  kind: CronHealthKind;
  total: number;
  actionable: number;
  quiet: number;
}

const QUIET_CORE =
  /^(?:dry-run\s*[-–—:]\s*)?(nothing to check|checked \d+, no repairs needed|no stale\b.*|completed|no log file yet|log is empty|no recent runs)\.?$/i;

const ACTIONABLE_DETAIL = /can be freed|\[delete\]|\[keep\]|blocker|fail|error/i;

/**
 * Quiet = healthy noise to collapse. Actionable = everything else.
 * Quiet only when status is `ok` (default), exit is zero/absent, no applied repairs,
 * no fatal, and detail matches healthy no-op patterns.
 * Actionable detail tokens are checked before quiet-core so greedy patterns like
 * `no stale\b.*` cannot hide blockers or freeable-space notes.
 */
export const isQuietRun = (
  run: Pick<MediaStackCronLogRunDto, 'status' | 'applied' | 'fatal' | 'detail' | 'exitCode'>,
): boolean => {
  const status = (run.status || 'ok').trim().toLowerCase();
  if (status !== 'ok') return false;
  if (typeof run.exitCode === 'number' && run.exitCode !== 0) return false;
  if (typeof run.applied === 'number' && run.applied > 0) return false;
  if (run.fatal) return false;

  const detail = (run.detail || '').trim();
  if (!detail) return true;
  if (ACTIONABLE_DETAIL.test(detail)) return false;
  if (QUIET_CORE.test(detail)) return true;
  if (/^(?:dry-run\s*[-–—:]\s*)?no .+\.?$/i.test(detail) && !/error|fail|warn/i.test(detail)) return true;
  return false;
};

export const isActionableRun = (
  run: Pick<MediaStackCronLogRunDto, 'status' | 'applied' | 'fatal' | 'detail' | 'exitCode'>,
): boolean => !isQuietRun(run);

export const normalizeCronRun = (
  job: Pick<MediaStackCronLogEntryDto, 'id' | 'title'>,
  run: MediaStackCronLogRunDto,
  index: number,
): CronRun => {
  const status = run.status?.trim() || 'ok';
  return {
    id: `${job.id}-${run.timestamp ?? 'unknown'}-${index}`,
    jobId: job.id,
    jobTitle: job.title,
    status,
    triage: isQuietRun(run) ? 'quiet' : 'actionable',
    timestamp: run.timestamp ?? '',
    detail: run.detail?.trim() ?? '',
    fatal: run.fatal ?? null,
    applied: typeof run.applied === 'number' ? run.applied : null,
    exitCode: typeof run.exitCode === 'number' ? run.exitCode : null,
  };
};

/** Build a triage row for jobs that have entry metadata but no nested runs. */
export const synthesizeCronRunFromEntry = (job: MediaStackCronLogEntryDto): CronRun => {
  const status = job.lastStatus?.trim() || (job.exists ? 'unparsed' : 'missing');
  const detail =
    job.summary?.trim() || (job.exists ? 'No recent runs' : 'No log file yet');
  return normalizeCronRun(
    job,
    {
      status,
      detail,
      timestamp: job.mtime ?? undefined,
    },
    0,
  );
};

export const flattenCronRuns = (dto: MediaStackCronLogsDto): CronRun[] =>
  (dto.logs ?? []).flatMap((job) => {
    const runs = job.runs ?? [];
    if (runs.length === 0) return [synthesizeCronRunFromEntry(job)];
    return runs.map((run, index) => normalizeCronRun(job, run, index));
  });

const triageRank = (triage: CronRunTriage): number => (triage === 'actionable' ? 0 : 1);

const actionableSeverityRank = (status: string): number => {
  const normalized = status.toLowerCase();
  if (normalized === 'fatal') return 0;
  if (normalized === 'warn' || normalized === 'applied') return 1;
  if (normalized === 'unparsed' || normalized === 'missing') return 2;
  return 3;
};

/** Actionable first (fatal before softer actionable), then quiet; newest timestamp within each band. */
export const prioritizeCronRuns = (runs: CronRun[]): CronRun[] =>
  [...runs].sort((left, right) => {
    const byTriage = triageRank(left.triage) - triageRank(right.triage);
    if (byTriage !== 0) return byTriage;
    if (left.triage === 'actionable') {
      const bySeverity = actionableSeverityRank(left.status) - actionableSeverityRank(right.status);
      if (bySeverity !== 0) return bySeverity;
    }
    const byTime = (right.timestamp || '').localeCompare(left.timestamp || '');
    if (byTime !== 0) return byTime;
    return left.jobTitle.localeCompare(right.jobTitle);
  });

export const summarizeCronHealth = (runs: CronRun[]): CronHealthSummary => {
  const total = runs.length;
  const actionable = runs.filter((run) => run.triage === 'actionable').length;
  const quiet = total - actionable;
  if (total === 0) return { kind: 'empty', total: 0, actionable: 0, quiet: 0 };
  if (actionable === 0) return { kind: 'allClear', total, actionable: 0, quiet };
  return { kind: 'mixed', total, actionable, quiet };
};

export const normalizeLibraryItem = (dto: MediaStackLibraryItemDto): LibraryItem | null => {
  const kind = normalizeLibraryKind(dto.kind);
  if (!kind) return null;
  const artworkState = normalizeArtworkState(dto.artworkState, dto.posterUrl);
  return {
    id: dto.id?.trim() || 'unknown',
    title: dto.title?.trim() || 'Untitled',
    kind,
    meta: formatLibraryMeta(dto.year, kind),
    art: resolveLibraryArt(dto.posterUrl, artworkState),
    overview: dto.overview?.trim() || '',
    href: null,
    artworkState,
    playable: dto.playable !== false,
  };
};

export const resolveJellyfinItemLink = (
  item: Pick<LibraryItem, 'id' | 'playable'>,
  bases: JellyfinLinkBases = {},
): string | null => {
  if (!item.playable || !item.id || item.id === 'unknown') return null;
  const jellyfinBase = (bases.jellyfinBase ?? DEFAULT_JELLYFIN_LINK_BASES.jellyfinBase).replace(/\/$/, '');
  if (!jellyfinBase) return null;
  return `${jellyfinBase}/web/index.html#!/details?id=${encodeURIComponent(item.id)}`;
};

export const formatLibraryMeta = (year: number | undefined, kind: LibraryItemKind): string => {
  const kindLabel = kind === 'movie' ? 'Movie' : 'Series';
  return Number.isFinite(year) && year ? `${year} · ${kindLabel}` : kindLabel;
};

function normalizeLibraryKind(kind: string | undefined): LibraryItemKind | null {
  const normalized = kind?.trim().toLowerCase();
  if (normalized === 'movie') return 'movie';
  if (normalized === 'series') return 'series';
  return null;
}

function normalizeArtworkState(
  state: LibraryArtworkState | undefined,
  posterUrl: string | undefined,
): LibraryArtworkState {
  if (state === 'failed' || state === 'missing' || state === 'ok') return state;
  return posterUrl?.trim() ? 'ok' : 'missing';
}

function resolveLibraryArt(posterUrl: string | undefined, artworkState: LibraryArtworkState): string {
  if (artworkState === 'missing' || artworkState === 'failed') return DEFAULT_LIBRARY_ART;
  const value = posterUrl?.trim();
  if (!value) return DEFAULT_LIBRARY_ART;
  if (value.startsWith('url(') || value.includes('gradient(')) return value;
  return `url("${value}") center / cover no-repeat`;
}

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

// ---------------------------------------------------------------------------
// Automation summary boundary
// ---------------------------------------------------------------------------

export type MediaStackAutomationServiceStatusDto =
  | 'healthy'
  | 'degraded'
  | 'down'
  | 'unknown';

export interface MediaStackAutomationServiceDto {
  id: string;
  name: string;
  status: string;
  detail?: string;
}

export interface MediaStackAutomationPreviewItemDto {
  id: string;
  title: string;
  when?: string;
  kind?: string;
}

export interface MediaStackAutomationProblemDto {
  id: string;
  summary: string;
  serviceId?: string;
  severity?: string;
}

export interface MediaStackAutomationSummaryDto {
  generatedAt: string;
  services?: MediaStackAutomationServiceDto[] | null;
  preview?: MediaStackAutomationPreviewItemDto[] | null;
  problems?: MediaStackAutomationProblemDto[] | null;
  unavailable?: {
    services?: boolean;
    preview?: boolean;
    problems?: boolean;
  };
}

export type AutomationServiceStatus = 'healthy' | 'degraded' | 'down' | 'unknown';
export type AutomationProblemSeverity = 'actionable' | 'warning' | 'info';

export interface AutomationService {
  id: string;
  name: string;
  status: AutomationServiceStatus;
  detail: string;
}

export interface AutomationPreviewItem {
  id: string;
  title: string;
  when: string;
  kind: string;
}

export interface AutomationProblem {
  id: string;
  summary: string;
  serviceId: string | null;
  severity: AutomationProblemSeverity;
}

export interface AutomationSectionAvailability {
  services: 'present' | 'empty' | 'unavailable';
  preview: 'present' | 'empty' | 'unavailable';
  problems: 'present' | 'empty' | 'unavailable';
}

export interface AutomationSummary {
  generatedAt: string;
  services: AutomationService[];
  preview: AutomationPreviewItem[];
  problems: AutomationProblem[];
  availability: AutomationSectionAvailability;
}

const AUTOMATION_SERVICE_STATUSES: AutomationServiceStatus[] = ['healthy', 'degraded', 'down', 'unknown'];
const AUTOMATION_PROBLEM_SEVERITIES: AutomationProblemSeverity[] = ['actionable', 'warning', 'info'];

const STATUS_RANK: Record<AutomationServiceStatus, number> = {
  down: 0,
  degraded: 1,
  unknown: 2,
  healthy: 3,
};

function normalizeAutomationStatus(status: string): AutomationServiceStatus {
  const normalized = status?.toLowerCase() ?? '';
  return AUTOMATION_SERVICE_STATUSES.includes(normalized as AutomationServiceStatus)
    ? (normalized as AutomationServiceStatus)
    : 'unknown';
}

function normalizeAutomationSeverity(severity: string): AutomationProblemSeverity {
  const normalized = severity?.toLowerCase() ?? '';
  return AUTOMATION_PROBLEM_SEVERITIES.includes(normalized as AutomationProblemSeverity)
    ? (normalized as AutomationProblemSeverity)
    : 'info';
}

function deriveSectionAvailability<T>(
  items: T[] | null | undefined,
  unavailableFlag: boolean | undefined,
): 'present' | 'empty' | 'unavailable' {
  if (unavailableFlag) return 'unavailable';
  if (items == null) return 'unavailable';
  return items.length > 0 ? 'present' : 'empty';
}

export const normalizeAutomationSummary = (dto: MediaStackAutomationSummaryDto): AutomationSummary => ({
  generatedAt: dto.generatedAt ?? '',
  services: (dto.services ?? []).map((service) => ({
    id: service.id ?? '',
    name: service.name ?? '',
    status: normalizeAutomationStatus(service.status),
    detail: service.detail ?? '',
  })),
  preview: (dto.preview ?? []).map((item) => ({
    id: item.id ?? '',
    title: item.title ?? '',
    when: item.when ?? '',
    kind: item.kind ?? '',
  })),
  problems: (dto.problems ?? []).map((problem) => ({
    id: problem.id ?? '',
    summary: problem.summary ?? '',
    serviceId: problem.serviceId ?? null,
    severity: normalizeAutomationSeverity(problem.severity ?? 'info'),
  })),
  availability: {
    services: deriveSectionAvailability(dto.services, dto.unavailable?.services),
    preview: deriveSectionAvailability(dto.preview, dto.unavailable?.preview),
    problems: deriveSectionAvailability(dto.problems, dto.unavailable?.problems),
  },
});

export interface AutomationHealthSummary {
  overall: AutomationServiceStatus;
  actionableCount: number;
}

export const summarizeAutomationHealth = (summary: AutomationSummary): AutomationHealthSummary => {
  const sortedServices = [...summary.services].sort(
    (left, right) => STATUS_RANK[left.status] - STATUS_RANK[right.status],
  );
  const overall = sortedServices[0]?.status ?? 'unknown';
  const actionableCount = summary.problems.filter((problem) => problem.severity === 'actionable').length;
  return { overall, actionableCount };
};

