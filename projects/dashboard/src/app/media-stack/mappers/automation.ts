import {
  AutomationProblemSeverity,
  AutomationServiceStatus,
  AutomationSummary,
} from '../../automation/automation.models';
import { MediaStackAutomationSummaryDto } from '../wire/automation';

const AUTOMATION_SERVICE_STATUSES: AutomationServiceStatus[] = ['healthy', 'degraded', 'down', 'unknown'];
const AUTOMATION_PROBLEM_SEVERITIES: AutomationProblemSeverity[] = ['actionable', 'warning', 'info'];

function normalizeAutomationStatus(status: string): AutomationServiceStatus {
  const normalized = status?.toLowerCase() ?? '';
  return AUTOMATION_SERVICE_STATUSES.includes(normalized as AutomationServiceStatus)
    ? (normalized as AutomationServiceStatus)
    : 'unknown';
}

function normalizeAutomationSeverity(severity: string): AutomationProblemSeverity {
  const normalized = severity?.toLowerCase() ?? '';
  return AUTOMATION_PROBLEM_SEVERITIES.includes(normalized as AutomationProblemSeverity)
    ? (normalized as AutomationProblemSeverity)
    : 'info';
}

function deriveSectionAvailability<T>(
  items: T[] | null | undefined,
  unavailableFlag: boolean | undefined,
): 'present' | 'empty' | 'unavailable' {
  if (unavailableFlag) return 'unavailable';
  if (items == null) return 'unavailable';
  return items.length > 0 ? 'present' : 'empty';
}

export const mapAutomationSummary = (dto: MediaStackAutomationSummaryDto): AutomationSummary => ({
  generatedAt: dto.generatedAt ?? '',
  services: (dto.services ?? []).map((service) => ({
    id: service.id ?? '',
    name: service.name ?? '',
    status: normalizeAutomationStatus(service.status),
    detail: service.detail ?? '',
  })),
  preview: (dto.preview ?? []).map((item) => ({
    id: item.id ?? '',
    title: item.title ?? '',
    when: item.when ?? '',
    kind: item.kind ?? '',
  })),
  problems: (dto.problems ?? []).map((problem) => ({
    id: problem.id ?? '',
    summary: problem.summary ?? '',
    serviceId: problem.serviceId ?? null,
    severity: normalizeAutomationSeverity(problem.severity ?? 'info'),
  })),
  availability: {
    services: deriveSectionAvailability(dto.services, dto.unavailable?.services),
    preview: deriveSectionAvailability(dto.preview, dto.unavailable?.preview),
    problems: deriveSectionAvailability(dto.problems, dto.unavailable?.problems),
  },
});
