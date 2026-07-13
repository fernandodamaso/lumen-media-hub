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

export interface MediaStackApi {
  listTorrents(): Promise<MediaStackTorrentDto[]>;
  pauseAll(): Promise<void>;
  resumeAll(): Promise<void>;
  listCalendarEvents(): Promise<MediaStackCalendarEventDto[]>;
  getArrLibrary(): Promise<MediaStackArrLibraryDto>;
  getAutomationSummary(): Promise<MediaStackAutomationSummaryDto>;
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

