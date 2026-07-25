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
}

export interface AutomationProblem {
  id: string;
  summary: string;
  serviceId: string | null;
  severity: AutomationProblemSeverity;
  items?: AutomationProblemItem[];
  itemCount?: number | null;
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

export const compareAutomationServices = (a: AutomationService, b: AutomationService): number =>
  STATUS_RANK[a.status] - STATUS_RANK[b.status];

export const summarizeAutomationHealth = (summary: AutomationSummary): AutomationHealthSummary => {
  const sortedServices = [...summary.services].sort(compareAutomationServices);
  const overall = sortedServices[0]?.status ?? 'unknown';
  const actionableCount = summary.problems.filter((problem) => problem.severity === 'actionable').length;
  return { overall, actionableCount };
};
