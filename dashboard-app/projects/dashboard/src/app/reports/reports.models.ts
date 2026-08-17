type CronRunTriage = 'actionable' | 'quiet';
type CronHealthKind = 'empty' | 'allClear' | 'mixed';

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
  schedule?: string;
}

/** An older run retained for inspection; `resolved` when a later run was quiet. */
export interface CronHistoricalRun extends CronRun {
  resolved: boolean;
}

/**
 * Job-based current-health summary. `totalJobs` is the number of configured jobs;
 * `affectedJobs` counts jobs whose current run is actionable; `healthyJobs` the rest.
 */
export interface CronHealthSummary {
  kind: CronHealthKind;
  totalJobs: number;
  affectedJobs: number;
  healthyJobs: number;
}

/** Domain envelope returned by the media-stack port (current/history already separated). */
export interface CronLogs {
  ok: boolean;
  generatedAt?: string;
  error?: string;
  currentRuns: CronRun[];
  historyRuns: CronHistoricalRun[];
}

/** Loose input for triage helpers (wire runs before mapping, or domain CronRun fields). */
export type CronTriageInput = {
  status?: string;
  applied?: number | null;
  fatal?: string | null;
  detail?: string;
  exitCode?: number | null;
};

const QUIET_CORE =
  /^(?:dry-run\s*[-–—:]\s*)?(nothing to check|checked \d+, no repairs needed|no stale\b.*|completed|all services are healthy|no log file yet|log is empty|no recent runs)\.?$/i;

const BLOCKER_DETAIL = /\[delete\]|\[keep\]|blocker|fail|error/i;

/** Constant for successful Weekly Validate report blocks, e.g. `Phase completed: 6 (Tasks 19-20)`. */
const PHASE_COMPLETED = /^phase completed\s*:\s*\S/i;

/**
 * Quiet = healthy noise to collapse. Actionable = everything else.
 * Quiet only when status is `ok` (default), exit is zero/absent, no applied repairs,
 * no fatal, and detail matches healthy no-op patterns.
 * Actionable detail tokens/positive freeable-space notes are checked before quiet-core
 * so greedy patterns like `no stale\b.*` cannot hide blockers.
 */
export const isQuietRun = (run: CronTriageInput): boolean => {
  const status = (run.status || 'ok').trim().toLowerCase();
  if (status !== 'ok') return false;
  if (typeof run.exitCode === 'number' && run.exitCode !== 0) return false;
  if (typeof run.applied === 'number' && run.applied > 0) return false;
  if (run.fatal) return false;

  const detail = (run.detail || '').trim();
  if (!detail) return true;
  if (BLOCKER_DETAIL.test(detail)) return false;
  // Numeric zero-work cleanup ("0 file(s) can be freed") is quiet; a positive value
  // or an unparseable freeable-space phrase stays actionable. The number is the token
  // immediately before the unit preceding "can be freed".
  const freedIndex = detail.search(/can be freed/i);
  if (freedIndex !== -1) {
    const before = detail.slice(0, freedIndex).trim();
    const tokens = before.split(/\s+/);
    const numberToken = tokens.length >= 2 ? tokens[tokens.length - 2] : tokens[0] ?? '';
    const value = Number(numberToken);
    if (Number.isFinite(value)) return value === 0;
    return false;
  }
  if (PHASE_COMPLETED.test(detail)) return true;
  if (QUIET_CORE.test(detail)) return true;
  if (/^(?:dry-run\s*[-–—:]\s*)?no [^\r\n]*$/i.test(detail) && !/error|fail|warn/i.test(detail)) return true;
  // Actionable = everything else: unparseable `can be freed` and unknown detail stay actionable.
  return false;
};

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
  const totalJobs = runs.length;
  const affectedJobs = runs.filter((run) => run.triage === 'actionable').length;
  const healthyJobs = totalJobs - affectedJobs;
  if (totalJobs === 0) {
    return { kind: 'empty', totalJobs: 0, affectedJobs: 0, healthyJobs: 0 };
  }
  if (affectedJobs === 0) return { kind: 'allClear', totalJobs, affectedJobs: 0, healthyJobs };
  return { kind: 'mixed', totalJobs, affectedJobs, healthyJobs };
};
