import { AutomationProblemSeverity, AutomationServiceStatus } from '../media-stack/media-stack-api';

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
