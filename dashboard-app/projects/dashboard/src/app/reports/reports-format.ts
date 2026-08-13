import { AutomationProblem, AutomationService } from '../automation/automation.models';
import { CronLogs, CronRun, isQuietRun } from './reports.models';
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
  const timestamp = run.timestamp?.trim() ?? '';
  // Identity is composed only from backend job id + backend timestamp (or entry sentinel).
  const id = timestamp ? `${job.id}-${timestamp}-${index}` : `${job.id}-entry`;
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

/** Build a triage row for jobs that have entry metadata but no nested runs. */
const synthesizeCronRunFromEntry = (job: MediaStackCronLogEntryDto): CronRun => {
  const status = job.lastStatus?.trim() || (job.exists ? 'unparsed' : 'missing');
  const detail = job.summary?.trim() || (job.exists ? 'No recent runs' : 'No log file yet');
  return mapCronRun(
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
    return runs.map((run, index) => mapCronRun(job, run, index));
  });

export const mapCronLogs = (dto: MediaStackCronLogsDto): CronLogs => ({
  ok: dto.ok,
  generatedAt: dto.generatedAt,
  error: dto.error,
  runs: flattenCronRuns(dto),
});

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
