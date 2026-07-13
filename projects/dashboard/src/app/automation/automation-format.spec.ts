import {
  AUTOMATION_PROBLEM_SEVERITY_VIEW,
  AUTOMATION_SERVICE_STATUS_VIEW,
  formatGeneratedAt,
} from './automation-format';

describe('automation-format', () => {
  it.each([
    ['healthy', 'Healthy', 'success'],
    ['degraded', 'Degraded', 'warning'],
    ['down', 'Down', 'danger'],
    ['unknown', 'Unknown', 'info'],
  ] as const)('maps service status %s to label %s and tone %s', (status, label, tone) => {
    expect(AUTOMATION_SERVICE_STATUS_VIEW[status]).toEqual({ label, tone });
  });

  it.each([
    ['actionable', 'Needs attention', 'danger'],
    ['warning', 'Warning', 'warning'],
    ['info', 'Notice', 'info'],
  ] as const)('maps problem severity %s to label %s and tone %s', (severity, label, tone) => {
    expect(AUTOMATION_PROBLEM_SEVERITY_VIEW[severity]).toEqual({ label, tone });
  });

  it('formats a valid ISO timestamp as a locale-friendly short datetime', () => {
    const formatted = formatGeneratedAt('2026-07-12T18:30:00Z');
    expect(formatted).toContain('Jul');
    expect(formatted).toContain('12');
    expect(formatted).toContain(':');
  });

  it('reports unavailable generated time for empty or invalid timestamps', () => {
    expect(formatGeneratedAt('')).toBe('Generated time unavailable');
    expect(formatGeneratedAt('not-a-date')).toBe('Generated time unavailable');
  });
});
