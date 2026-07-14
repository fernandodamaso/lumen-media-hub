import { CronLogs, CronRun, isQuietRun } from '../../reports/reports.models';
import {
  MediaStackCronLogEntryDto,
  MediaStackCronLogRunDto,
  MediaStackCronLogsDto,
} from '../wire/cron';

export const mapCronRun = (
  job: Pick<MediaStackCronLogEntryDto, 'id' | 'title'> & Partial<Pick<MediaStackCronLogEntryDto, 'schedule'>>,
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
