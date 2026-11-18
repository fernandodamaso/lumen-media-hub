export interface MediaStackAutomationServiceDto {
  id: string;
  name: string;
  status: string;
  detail?: string;
  latencyMs?: number | null;
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
  /** Episode/movie rows when the problem is an aggregate missing/wanted summary. */
  items?: MediaStackAutomationProblemItemDto[] | null;
  /** Total count from the service block when items may be truncated. */
  itemCount?: number | null;
}

export interface MediaStackAutomationProblemItemDto {
  title: string;
  when?: string;
  /** Deep link into the service UI (e.g. Sonarr series page) when available. */
  href?: string | null;
  posterUrl?: string | null;
}

type MediaStackQueueHygieneModeDto = 'off' | 'observe' | 'auto';
type MediaStackQueueHygieneStatusDto =
  | 'observed'
  | 'cleaned'
  | 'circuit_open'
  | 'verification_failed'
  | 'error'
  | 'skipped'
  | 'off';

export interface MediaStackQueueHygieneEligibleItemDto {
  downloadId: string;
  queueIds: number[];
  titles: string[];
  reason: string;
  completedAt: string;
  ageHours: number;
}

export interface MediaStackQueueHygieneBlockedItemDto {
  queueId: number | null;
  title: string;
  reason: string;
  blocker: string;
}

interface MediaStackQueueHygieneVerificationDto {
  queueIdsGone: boolean;
  hashesPreserved: boolean;
  missingHashes: string[];
}

interface MediaStackQueueHygieneCleanupDto {
  at: string;
  queueIds: number[];
  hashes: string[];
}

export interface MediaStackQueueHygieneSummaryDto {
  mode: MediaStackQueueHygieneModeDto;
  circuitOpen: boolean;
  eligibleCount: number;
  blockedCount: number;
  eligibleItems: MediaStackQueueHygieneEligibleItemDto[];
  blockedItems: MediaStackQueueHygieneBlockedItemDto[];
  lastCycleAt: string | null;
  lastCleanup: MediaStackQueueHygieneCleanupDto | null;
  verification: MediaStackQueueHygieneVerificationDto | null;
  error?: string;
}

export interface MediaStackQueueHygieneRunResultDto extends MediaStackQueueHygieneSummaryDto {
  status: MediaStackQueueHygieneStatusDto;
  observedAt?: string;
  counts?: { eligible: number; blocked: number; queued: number };
}

export interface MediaStackAutomationSummaryDto {
  generatedAt: string;
  services?: MediaStackAutomationServiceDto[] | null;
  preview?: MediaStackAutomationPreviewItemDto[] | null;
  problems?: MediaStackAutomationProblemDto[] | null;
  queueHygiene?: MediaStackQueueHygieneSummaryDto | null;
  status?: MediaStackOperationalStatusDto | null;
  unavailable?: {
    services?: boolean;
    preview?: boolean;
    problems?: boolean;
  };
}

interface MediaStackOperationalDiskDto {
  id: string;
  label: string;
  status: string;
  identityStatus: string;
  availableBytes: number | null;
  freeBytes: number | null;
  usedBytes: number | null;
  totalBytes: number | null;
}

export interface MediaStackOperationalStatusDto {
  generatedAt: string;
  storage: {
    status: string;
    disks: MediaStackOperationalDiskDto[];
  };
  pause: {
    status: string;
    reason: string;
    manual: boolean | null;
    guard: boolean | null;
    known: boolean;
  };
  guard: {
    enabled: boolean;
    status: string;
    health: string;
    lastCycleAt: string | null;
  };
  verifiedCleanup: {
    enabled: boolean;
    status: string;
    lastResult: { status: string; reason?: string | null } | null;
    queueCount: number;
    scheduler?: {
      running: boolean;
      lastCycleAt: string | null;
      lastStatus: string | null;
      lastError: string | null;
    } | null;
  };
  verification: {
    status: string;
    queuedCount: number;
    previewCount: number;
  };
  trakt: {
    configured: boolean;
    auth: string;
    health: string;
    expiresAt: string | null;
  };
  retention: {
    enabled: boolean;
    status: string;
    preview: { eligibleCount: number; preservedCount: number } | null;
    skips: { reason: string; count: number }[];
    results: { deletedCount: number; preservedCount: number; pendingCount: number };
    lastResult: { status: string; reason?: string | null } | null;
    scheduler: { enabled: boolean; running: boolean };
  };
}
