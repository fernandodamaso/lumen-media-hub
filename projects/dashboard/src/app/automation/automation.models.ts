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

interface AutomationProblem {
  id: string;
  summary: string;
  serviceId: string | null;
  severity: AutomationProblemSeverity;
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

export const summarizeAutomationHealth = (summary: AutomationSummary): AutomationHealthSummary => {
  const sortedServices = [...summary.services].sort(
    (left, right) => STATUS_RANK[left.status] - STATUS_RANK[right.status],
  );
  const overall = sortedServices[0]?.status ?? 'unknown';
  const actionableCount = summary.problems.filter((problem) => problem.severity === 'actionable').length;
  return { overall, actionableCount };
};
