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
  schedule?: string;
}

export interface CronHealthSummary {
  kind: CronHealthKind;
  total: number;
  actionable: number;
  quiet: number;
}

/** Domain envelope returned by the media-stack port (runs already flattened). */
export interface CronLogs {
  ok: boolean;
  generatedAt?: string;
  error?: string;
  runs: CronRun[];
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

const ACTIONABLE_DETAIL = /can be freed|\[delete\]|\[keep\]|blocker|fail|error/i;

/**
 * Quiet = healthy noise to collapse. Actionable = everything else.
 * Quiet only when status is `ok` (default), exit is zero/absent, no applied repairs,
 * no fatal, and detail matches healthy no-op patterns.
 * Actionable detail tokens are checked before quiet-core so greedy patterns like
 * `no stale\b.*` cannot hide blockers or freeable-space notes.
 */
export const isQuietRun = (run: CronTriageInput): boolean => {
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

export const isActionableRun = (run: CronTriageInput): boolean => !isQuietRun(run);

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
