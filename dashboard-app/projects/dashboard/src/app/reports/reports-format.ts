import { AutomationProblem, AutomationService } from '../automation/automation.models';
import { CronHistoricalRun, CronLogs, CronRun, isQuietRun } from './reports.models';
import {
  MediaStackCronLogEntryDto,
  MediaStackCronLogRunDto,
  MediaStackCronLogsDto,
} from '../media-stack/wire/cron';

type StatusTone = 'success' | 'warning' | 'danger' | 'info';

export type CronStatusView = { label: string; tone: StatusTone };

const STATUS_VIEWS: Record<string, CronStatusView> = {
  ok: { label: 'ok', tone: 'success' },
  fatal: { label: 'failed', tone: 'danger' },
  applied: { label: 'repaired', tone: 'success' },
  warn: { label: 'warn', tone: 'warning' },
  unparsed: { label: 'unknown', tone: 'info' },
  missing: { label: 'no log', tone: 'info' },
};

export function cronStatusView(status: string | null | undefined): CronStatusView {
  const key = (status || 'ok').toLowerCase();
  return STATUS_VIEWS[key] ?? { label: key, tone: 'info' };
}

export function formatGeneratedAt(iso: string): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function formatRunTimestamp(iso: string): string {
  if (!iso) return 'Unknown time';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export const mapCronRun = (
  job: Pick<MediaStackCronLogEntryDto, 'id' | 'title'> & Partial<Pick<MediaStackCronLogEntryDto, 'schedule'>>,
  run: MediaStackCronLogRunDto,
  index: number,
): CronRun => {
  const status = run.status?.trim() || 'ok';
  const timestamp = typeof run.timestamp === 'string' ? run.timestamp.trim() : '';
  // Identity composed from backend job id + timestamp-or-unknown + source index so
  // malformed/missing timestamps cannot collide.
  const id = `${job.id}-${timestamp || 'unknown'}-${index}`;
  return {
    id,
    jobId: job.id,
    jobTitle: job.title,
    status,
    triage: isQuietRun(run) ? 'quiet' : 'actionable',
    timestamp,
    detail: run.detail?.trim() ?? '',
    fatal: run.fatal ?? null,
    applied: typeof run.applied === 'number' ? run.applied : null,
    exitCode: typeof run.exitCode === 'number' ? run.exitCode : null,
    schedule: job.schedule || 'Not scheduled',
  };
};

export const mapCronLogs = (dto: MediaStackCronLogsDto): CronLogs => {
  const currentRuns: CronRun[] = [];
  const historyRuns: CronHistoricalRun[] = [];
  for (const job of dto.logs ?? []) {
    const history: CronHistoricalRun[] = job.history.map((run, index) => ({
      ...mapCronRun(job, run, index),
      resolved: false,
    }));
    const current: CronRun = mapCronRun(job, job.current, history.length + 1);

    // Mark historical actionable rows resolved when a later run for the job is quiet.
    // Scan newest-to-oldest (history… then current). A later fatal does not re-open.
    const chronological = [...history, current];
    let seenQuiet = false;
    for (let i = chronological.length - 1; i >= 0; i--) {
      const row = chronological[i];
      if (row.triage === 'quiet') {
        seenQuiet = true;
        continue;
      }
      if (seenQuiet && i < history.length) {
        history[i] = { ...history[i], resolved: true };
      }
    }

    currentRuns.push(current);
    historyRuns.push(...history);
  }
  return {
    ok: dto.ok,
    generatedAt: dto.generatedAt,
    error: dto.error,
    currentRuns,
    historyRuns,
  };
};

export interface ServiceHealthReportView {
  unknownServiceNotice: string | null;
  services: AutomationService[];
  problems: AutomationProblem[];
  noIssuesMessage: string | null;
}

const NO_LIVE_ISSUES = 'No current live issues.';
const UNKNOWN_SERVICE_NOTICE = 'Unknown service. Showing all current issues.';

const activeServices = (services: AutomationService[]): AutomationService[] =>
  services.filter((service) => service.status === 'degraded' || service.status === 'down');

const problemsForService = (problems: AutomationProblem[], serviceId: string): AutomationProblem[] =>
  problems.filter((problem) => problem.serviceId === serviceId);

const activeProblems = (
  problems: AutomationProblem[],
  services: AutomationService[],
): AutomationProblem[] => {
  const activeIds = new Set(activeServices(services).map((service) => service.id));
  return problems.filter(
    (problem) => problem.serviceId == null || (problem.serviceId && activeIds.has(problem.serviceId)),
  );
};

const buildUnfilteredView = (
  services: AutomationService[],
  problems: AutomationProblem[],
): ServiceHealthReportView => {
  const matchedServices = activeServices(services);
  const matchedProblems = activeProblems(problems, services);
  const hasIssues = matchedServices.length > 0 || matchedProblems.length > 0;
  return {
    unknownServiceNotice: null,
    services: matchedServices,
    problems: matchedProblems,
    noIssuesMessage: hasIssues ? null : NO_LIVE_ISSUES,
  };
};

export function buildServiceHealthReportView(
  services: AutomationService[],
  problems: AutomationProblem[],
  selectedServiceId: string | null,
): ServiceHealthReportView {
  const trimmed = selectedServiceId?.trim() ?? '';
  if (!trimmed) {
    return buildUnfilteredView(services, problems);
  }

  const selected = services.find((service) => service.id === trimmed);
  if (!selected) {
    return {
      ...buildUnfilteredView(services, problems),
      unknownServiceNotice: UNKNOWN_SERVICE_NOTICE,
    };
  }

  if (selected.status === 'healthy') {
    return {
      unknownServiceNotice: null,
      services: [selected],
      problems: [],
      noIssuesMessage: NO_LIVE_ISSUES,
    };
  }

  if (selected.status !== 'degraded' && selected.status !== 'down') {
    return {
      unknownServiceNotice: null,
      services: [selected],
      problems: [],
      noIssuesMessage: null,
    };
  }

  const matchedProblems = problemsForService(problems, trimmed);
  return {
    unknownServiceNotice: null,
    services: [selected],
    problems: matchedProblems,
    noIssuesMessage: null,
  };
}
