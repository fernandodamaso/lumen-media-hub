import {
  AutomationProblemSeverity,
  AutomationServiceStatus,
  AutomationSummary,
} from './automation.models';
import { MediaStackAutomationSummaryDto } from '../media-stack/wire/automation';

export type AutomationStatusTone = 'success' | 'warning' | 'danger' | 'info';

export interface AutomationStatusView {
  label: string;
  tone: AutomationStatusTone;
}

export const AUTOMATION_SERVICE_STATUS_VIEW: Record<AutomationServiceStatus, AutomationStatusView> = {
  healthy: { label: 'Healthy', tone: 'success' },
  degraded: { label: 'Degraded', tone: 'warning' },
  down: { label: 'Down', tone: 'danger' },
  unknown: { label: 'Unknown', tone: 'info' },
};

export const AUTOMATION_PROBLEM_SEVERITY_VIEW: Record<AutomationProblemSeverity, AutomationStatusView> = {
  actionable: { label: 'Needs attention', tone: 'danger' },
  warning: { label: 'Warning', tone: 'warning' },
  info: { label: 'Notice', tone: 'info' },
};

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

const AUTOMATION_SERVICE_STATUSES: AutomationServiceStatus[] = ['healthy', 'degraded', 'down', 'unknown'];
const AUTOMATION_PROBLEM_SEVERITIES: AutomationProblemSeverity[] = ['actionable', 'warning', 'info'];

export function formatGeneratedAt(isoTimestamp: string): string {
  if (!isoTimestamp) return 'Generated time unavailable';
  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.getTime())) return 'Generated time unavailable';
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function formatRelativeTime(isoTimestamp: string): string {
  if (!isoTimestamp) return '';
  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.getTime())) return '';
  const diffMs = date.getTime() - Date.now();
  const diffSec = Math.floor(Math.abs(diffMs) / 1000);
  const isFuture = diffMs >= 0;
  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return isFuture ? `in ${diffSec}s` : `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return isFuture ? `in ${diffMin}m` : `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return isFuture ? `in ${diffHr}h` : `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return isFuture ? `in ${diffDay}d` : `${diffDay}d ago`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
