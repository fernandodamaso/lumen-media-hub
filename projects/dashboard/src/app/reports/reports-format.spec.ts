import { cronStatusView, formatGeneratedAt, formatRunTimestamp } from './reports-format';

describe('reports-format', () => {
  it.each([
    ['ok', 'ok', 'success'],
    ['fatal', 'failed', 'danger'],
    ['warn', 'warn', 'warning'],
    ['applied', 'repaired', 'warning'],
    ['unparsed', 'unknown', 'info'],
    ['missing', 'no log', 'info'],
  ] as const)('maps status %s to label/tone', (status, label, tone) => {
    expect(cronStatusView(status)).toEqual({ label, tone });
  });

  it('falls back for unknown statuses without inventing failure tones', () => {
    expect(cronStatusView('custom')).toEqual({ label: 'custom', tone: 'info' });
    expect(cronStatusView('')).toEqual({ label: 'ok', tone: 'success' });
  });

  it('formats timestamps for display', () => {
    expect(formatGeneratedAt('')).toBe('');
    expect(formatRunTimestamp('')).toBe('Unknown time');
    expect(formatGeneratedAt('not-a-date')).toBe('not-a-date');
    expect(formatGeneratedAt('2026-07-12T12:00:00Z')).toBeTruthy();
    expect(formatRunTimestamp('2026-07-12T12:00:00Z')).toBeTruthy();
  });
});
