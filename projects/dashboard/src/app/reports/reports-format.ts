import { CronLogs, CronRun, isQuietRun } from './reports.models';
import {
  MediaStackCronLogEntryDto,
  MediaStackCronLogRunDto,
  MediaStackCronLogsDto,
} from '../media-stack/wire/cron';

export type StatusTone = 'success' | 'warning' | 'danger' | 'info';

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
export const synthesizeCronRunFromEntry = (job: MediaStackCronLogEntryDto): CronRun => {
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
