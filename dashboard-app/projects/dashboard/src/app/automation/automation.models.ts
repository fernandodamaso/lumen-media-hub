export type AutomationServiceStatus = 'healthy' | 'degraded' | 'down' | 'unknown';
export type AutomationProblemSeverity = 'actionable' | 'warning' | 'info';

export interface AutomationService {
  id: string;
  name: string;
  status: AutomationServiceStatus;
  detail: string;
  latencyMs?: number | null;
}

interface AutomationPreviewItem {
  id: string;
  title: string;
  when: string;
  kind: string;
}

export interface AutomationProblemItem {
  title: string;
  when: string;
  href: string | null;
  posterUrl: string | null;
}

export interface AutomationProblem {
  id: string;
  summary: string;
  serviceId: string | null;
  severity: AutomationProblemSeverity;
  items?: AutomationProblemItem[];
  itemCount?: number | null;
}

type QueueHygieneMode = 'off' | 'observe' | 'auto';
type QueueHygieneStatus =
  | 'observed'
  | 'cleaned'
  | 'circuit_open'
  | 'verification_failed'
  | 'error'
  | 'skipped'
  | 'off';

interface QueueHygieneEligibleItem {
  downloadId: string;
  queueIds: number[];
  titles: string[];
  reason: string;
  completedAt: string;
  ageHours: number;
}

interface QueueHygieneBlockedItem {
  queueId: number | null;
  title: string;
  reason: string;
  blocker: string;
}

interface QueueHygieneVerification {
  queueIdsGone: boolean;
  hashesPreserved: boolean;
  missingHashes: string[];
}

interface QueueHygieneCleanup {
  at: string;
  queueIds: number[];
  hashes: string[];
}

export interface QueueHygieneSummary {
  mode: QueueHygieneMode;
  circuitOpen: boolean;
  eligibleCount: number;
  blockedCount: number;
  eligibleItems: QueueHygieneEligibleItem[];
  blockedItems: QueueHygieneBlockedItem[];
  lastCycleAt: string | null;
  lastCleanup: QueueHygieneCleanup | null;
  verification: QueueHygieneVerification | null;
  error?: string;
}

export interface QueueHygieneRunResult extends QueueHygieneSummary {
  status: QueueHygieneStatus;
  observedAt?: string;
  counts?: { eligible: number; blocked: number; queued: number };
}

type AutomationSectionState = 'present' | 'empty' | 'unavailable';

interface AutomationSectionAvailability {
  services: AutomationSectionState;
  preview: AutomationSectionState;
  problems: AutomationSectionState;
}

export interface AutomationSummary {
  generatedAt: string;
  services: AutomationService[];
  preview: AutomationPreviewItem[];
  problems: AutomationProblem[];
  queueHygiene: QueueHygieneSummary | null;
  availability: AutomationSectionAvailability;
}

export interface AutomationHealthSummary {
  overall: AutomationServiceStatus;
  actionableCount: number;
}

const STATUS_RANK: Record<AutomationServiceStatus, number> = {
  down: 0,
  degraded: 1,
  unknown: 2,
  healthy: 3,
};

export const compareAutomationServices = (a: AutomationService, b: AutomationService): number =>
  STATUS_RANK[a.status] - STATUS_RANK[b.status];

export const summarizeAutomationHealth = (summary: AutomationSummary): AutomationHealthSummary => {
  const sortedServices = [...summary.services].sort(compareAutomationServices);
  const overall = sortedServices[0]?.status ?? 'unknown';
  const actionableCount = summary.problems.filter((problem) => problem.severity === 'actionable').length;
  return { overall, actionableCount };
};
