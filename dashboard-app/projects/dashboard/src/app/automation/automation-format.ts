import {
  AutomationProblem,
  AutomationProblemItem,
  AutomationProblemSeverity,
  AutomationServiceStatus,
  AutomationSummary,
} from './automation.models';
import { MediaStackAutomationSummaryDto } from '../media-stack/wire/automation';

type AutomationStatusTone = 'success' | 'warning' | 'danger' | 'info';

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
  generatedAt: wireText(dto.generatedAt),
  services: (dto.services ?? []).map((service) => ({
    id: wireText(service.id),
    name: wireText(service.name),
    status: normalizeAutomationStatus(service.status),
    detail: wireText(service.detail),
    latencyMs: normalizeLatencyMs(service.latencyMs),
  })),
  preview: (dto.preview ?? []).map((item) => ({
    id: wireText(item.id),
    title: wireText(item.title),
    when: wireText(item.when),
    kind: wireText(item.kind),
  })),
  problems: (dto.problems ?? []).map(
    (problem): AutomationProblem => ({
      id: wireText(problem.id),
      summary: wireText(problem.summary),
      serviceId: problem.serviceId ?? null,
      severity: normalizeAutomationSeverity(problem.severity),
      items: (problem.items ?? [])
        .filter((item) => wireText(item.title))
        .map(
          (item): AutomationProblemItem => ({
            title: wireText(item.title),
            when: wireText(item.when),
            href: normalizeOptionalUrl(item.href),
            posterUrl: normalizeOptionalUrl(item.posterUrl),
          }),
        ),
      itemCount: normalizeItemCount(problem.itemCount),
    }),
  ),
  availability: {
    services: deriveSectionAvailability(dto.services, dto.unavailable?.services),
    preview: deriveSectionAvailability(dto.preview, dto.unavailable?.preview),
    problems: deriveSectionAvailability(dto.problems, dto.unavailable?.problems),
  },
});

/** Soft wire strings may be missing even when the DTO marks them required. */
function wireText(value: string | null | undefined): string {
  return value ?? '';
}

function normalizeOptionalUrl(value: string | null | undefined): string | null {
  const normalized = value?.trim();
  return normalized || null;
}

function normalizeAutomationStatus(status: string | null | undefined): AutomationServiceStatus {
  const normalized = wireText(status).toLowerCase();
  return AUTOMATION_SERVICE_STATUSES.includes(normalized as AutomationServiceStatus)
    ? (normalized as AutomationServiceStatus)
    : 'unknown';
}

function normalizeLatencyMs(latencyMs: number | null | undefined): number | null {
  return typeof latencyMs === 'number' && Number.isFinite(latencyMs) && latencyMs >= 0
    ? Math.round(latencyMs)
    : null;
}

function normalizeItemCount(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? Math.round(value) : null;
}

function normalizeAutomationSeverity(severity: string | null | undefined): AutomationProblemSeverity {
  const normalized = wireText(severity || 'info').toLowerCase();
  return AUTOMATION_PROBLEM_SEVERITIES.includes(normalized as AutomationProblemSeverity)
    ? (normalized as AutomationProblemSeverity)
    : 'info';
}

function deriveSectionAvailability(
  items: readonly unknown[] | null | undefined,
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

export function formatShortDate(value: string): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' as const }),
  });
}

export function formatRelativeTime(isoTimestamp: string): string {
  if (!isoTimestamp) return '';
  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.getTime())) return '';
  const diffMs = date.getTime() - Date.now();
  const absSec = Math.floor(Math.abs(diffMs) / 1000);
  if (absSec < 5) return 'just now';
  return formatRelativeUnits(absSec, diffMs >= 0, date);
}

function formatRelativeUnits(absSec: number, isFuture: boolean, date: Date): string {
  const phrase = (amount: number, unit: string) =>
    isFuture ? `in ${amount}${unit}` : `${amount}${unit} ago`;
  if (absSec < 60) return phrase(absSec, 's');
  const absMin = Math.floor(absSec / 60);
  if (absMin < 60) return phrase(absMin, 'm');
  const absHr = Math.floor(absMin / 60);
  if (absHr < 24) return phrase(absHr, 'h');
  const absDay = Math.floor(absHr / 24);
  if (absDay < 30) return phrase(absDay, 'd');
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
