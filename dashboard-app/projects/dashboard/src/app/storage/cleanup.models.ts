export const CLEANUP_SCHEMA_VERSION = 1 as const;
export const CLEANUP_POLICY_STORAGE_KEY = 'lumen.storageGuardian.policy.v1';
export const CLEANUP_PINS_STORAGE_KEY = 'lumen.storageGuardian.pins.v1';
export const GIB = 1024 ** 3;

export type CleanupMediaKind = 'movie' | 'episode';
export type CleanupPreviewStatus = 'complete' | 'degraded';
export type CleanupRuleCode =
  | 'watched_movie_expired'
  | 'watched_episode_expired'
  | 'large_watched_file_stale';
export type CleanupBlockCode =
  | 'in_progress'
  | 'never_watched'
  | 'favorite'
  | 'manual_pin'
  | 'recent_addition'
  | 'no_matching_rule';

export interface CleanupPolicySettings {
  schemaVersion: 1;
  targetFreeBytes: number;
  rules: {
    watchedMovies: { enabled: boolean; retentionDays: number };
    watchedEpisodes: { enabled: boolean; retentionDays: number; keepLatestPerSeries: number };
    largeWatchedFiles: { enabled: boolean; minimumBytes: number; idleDays: number };
  };
  protections: { recentAdditionGraceDays: number };
}

export interface CleanupPreviewRequest extends Omit<CleanupPolicySettings, 'protections'> {
  protections: {
    recentAdditionGraceDays: number;
    pinnedCandidateIds: string[];
  };
}

export interface CleanupReason {
  code: CleanupRuleCode;
  evidence: Readonly<Record<string, number>>;
}

export interface CleanupCandidate {
  id: string;
  mediaKind: CleanupMediaKind;
  title: string;
  subtitle: string;
  href: string | null;
  sizeBytes: number;
  dateAdded: string;
  lastPlayedAt: string;
  recommended: boolean;
  reasons: CleanupReason[];
}

export interface CleanupBlockSummary {
  code: CleanupBlockCode;
  count: number;
  bytes: number;
}

export interface CleanupUnresolvedItem {
  id: string;
  title: string;
  mediaKind: CleanupMediaKind | 'unknown';
  reason: string;
}

export interface CleanupPreview {
  schemaVersion: 1;
  previewId: string;
  generatedAt: string;
  status: CleanupPreviewStatus;
  storage: {
    totalBytes: number;
    usedBytes: number;
    freeBytes: number;
    targetFreeBytes: number;
    requiredReclaimBytes: number;
    eligibleBytes: number;
    recommendedBytes: number;
    projectedFreeBytes: number;
    remainingShortfallBytes: number;
  };
  summary: {
    scannedFiles: number;
    eligibleFiles: number;
    recommendedFiles: number;
    protectedFiles: number;
    unresolvedFiles: number;
  };
  candidates: CleanupCandidate[];
  blocked: CleanupBlockSummary[];
  unresolved: CleanupUnresolvedItem[];
  warnings: string[];
}

export const DEFAULT_CLEANUP_POLICY: CleanupPolicySettings = {
  schemaVersion: CLEANUP_SCHEMA_VERSION,
  targetFreeBytes: 200 * GIB,
  rules: {
    watchedMovies: { enabled: true, retentionDays: 30 },
    watchedEpisodes: { enabled: true, retentionDays: 14, keepLatestPerSeries: 3 },
    largeWatchedFiles: { enabled: true, minimumBytes: 20 * GIB, idleDays: 90 },
  },
  protections: { recentAdditionGraceDays: 7 },
};

export function cloneCleanupPolicy(policy: CleanupPolicySettings): CleanupPolicySettings {
  return {
    schemaVersion: 1,
    targetFreeBytes: policy.targetFreeBytes,
    rules: {
      watchedMovies: { ...policy.rules.watchedMovies },
      watchedEpisodes: { ...policy.rules.watchedEpisodes },
      largeWatchedFiles: { ...policy.rules.largeWatchedFiles },
    },
    protections: { ...policy.protections },
  };
}
