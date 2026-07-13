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

export interface MediaStackApi {
  listTorrents(): Promise<MediaStackTorrentDto[]>;
  pauseAll(): Promise<void>;
  resumeAll(): Promise<void>;
  listCalendarEvents(): Promise<MediaStackCalendarEventDto[]>;
  getArrLibrary(): Promise<MediaStackArrLibraryDto>;
  listCronLogs(): Promise<MediaStackCronLogsDto>;
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
