import {
  AUTOMATION_PROBLEM_SEVERITY_VIEW,
  AUTOMATION_SERVICE_STATUS_VIEW,
  formatGeneratedAt,
  formatRelativeTime,
  formatShortDate,
  mapAutomationSummary,
} from './automation-format';

describe('automation format / automation mapping', () => {
  it('maps a healthy automation summary DTO into a domain summary', () => {
    const summary = mapAutomationSummary({
      generatedAt: '2026-07-12T18:00:00Z',
      services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK' }],
      preview: [{ id: 'p1', title: 'Dune', when: 'Jul 13', kind: 'movie' }],
      problems: [{ id: 'x1', summary: 'Disk low', serviceId: 'radarr', severity: 'actionable' }],
    });
    expect(summary.generatedAt).toBe('2026-07-12T18:00:00Z');
    expect(summary.services).toHaveLength(1);
    expect(summary.services[0].status).toBe('healthy');
    expect(summary.availability).toEqual({ services: 'present', preview: 'present', problems: 'present' });
  });

  it.each(['broken', 'OFFLINE', '', undefined as unknown as string])(
    'clamps unknown or missing automation status %j to unknown',
    (status) => {
      const summary = mapAutomationSummary({
        generatedAt: '',
        services: [{ id: 'x', name: 'X', status }],
      });
      expect(summary.services[0].status).toBe('unknown');
    },
  );

  it('defaults missing problem severity to info', () => {
    const summary = mapAutomationSummary({
      generatedAt: '',
      problems: [{ id: 'x', summary: 'X', severity: undefined }],
    });
    expect(summary.problems[0].severity).toBe('info');
  });

  it('passes through posterUrl on problem items and defaults to null when absent', () => {
    const summary = mapAutomationSummary({
      generatedAt: '',
      problems: [
        {
          id: 'x',
          summary: 'X',
          items: [
            { title: 'With Poster', when: 'Tonight', href: null, posterUrl: 'http://localhost:8989/MediaCover/13/poster-250.jpg' },
            { title: 'No Poster', when: 'Tomorrow', href: null },
          ],
        },
      ],
    });
    expect(summary.problems[0].items).toEqual([
      { title: 'With Poster', when: 'Tonight', href: null, posterUrl: 'http://localhost:8989/MediaCover/13/poster-250.jpg' },
      { title: 'No Poster', when: 'Tomorrow', href: null, posterUrl: null },
    ]);
  });

  it('passes through href on problem items and defaults to null when absent', () => {
    const summary = mapAutomationSummary({
      generatedAt: '',
      problems: [
        {
          id: 'x',
          summary: 'X',
          items: [
            { title: 'With Link', when: 'Tonight', href: 'http://example.com/link' },
            { title: 'No Link', when: 'Tomorrow' },
            { title: 'Blank Href', when: 'Later', href: '' },
            { title: 'Whitespace Poster', when: 'Soon', href: null, posterUrl: '   ' },
          ],
        },
      ],
    });
    expect(summary.problems[0].items).toEqual([
      { title: 'With Link', when: 'Tonight', href: 'http://example.com/link', posterUrl: null },
      { title: 'No Link', when: 'Tomorrow', href: null, posterUrl: null },
      { title: 'Blank Href', when: 'Later', href: null, posterUrl: null },
      { title: 'Whitespace Poster', when: 'Soon', href: null, posterUrl: null },
    ]);
  });

  it('marks null sections with unavailable flag as unavailable', () => {
    const summary = mapAutomationSummary({
      generatedAt: '',
      services: null,
      preview: [],
      unavailable: { services: true },
    });
    expect(summary.availability).toEqual({ services: 'unavailable', preview: 'empty', problems: 'unavailable' });
  });

  it('marks undefined/null sections without flag as unavailable', () => {
    const summary = mapAutomationSummary({
      generatedAt: '',
    });
    expect(summary.availability).toEqual({
      services: 'unavailable',
      preview: 'unavailable',
      problems: 'unavailable',
    });
  });

  it('defaults missing generatedAt and string fields to empty values', () => {
    const summary = mapAutomationSummary({
      generatedAt: undefined as unknown as string,
      services: [{ id: undefined as unknown as string, name: undefined as unknown as string, status: 'down' }],
      preview: [{ id: undefined as unknown as string, title: undefined as unknown as string }],
      problems: [{ id: undefined as unknown as string, summary: undefined as unknown as string }],
    });
    expect(summary.generatedAt).toBe('');
    expect(summary.services[0]).toEqual({ id: '', name: '', status: 'down', detail: '', latencyMs: null });
    expect(summary.preview[0]).toEqual({ id: '', title: '', when: '', kind: '' });
    expect(summary.problems[0]).toEqual({
      id: '',
      summary: '',
      serviceId: null,
      severity: 'info',
      items: [],
      itemCount: null,
    });
  });

  it('passes through service latencyMs and normalizes invalid values to null', () => {
    const summary = mapAutomationSummary({
      generatedAt: '',
      services: [
        { id: 'a', name: 'A', status: 'healthy', latencyMs: 18 },
        { id: 'b', name: 'B', status: 'down' },
        { id: 'c', name: 'C', status: 'healthy', latencyMs: Number.NaN },
      ],
    });
    expect(summary.services.map((service) => service.latencyMs)).toEqual([18, null, null]);
  });

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

  describe('formatShortDate', () => {
    it('returns empty string for empty input', () => {
      expect(formatShortDate('')).toBe('');
    });

    it('passes through non-date strings unchanged', () => {
      expect(formatShortDate('downloading')).toBe('downloading');
      expect(formatShortDate('Tonight')).toBe('Tonight');
    });

    it('formats current-year ISO date as short month + day', () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2026-07-15T12:00:00Z'));
      try {
        expect(formatShortDate('2026-03-24T14:00:00Z')).toBe('Mar 24');
      } finally {
        vi.useRealTimers();
      }
    });

    it('includes year when the date falls in a different year', () => {
      const result = formatShortDate('2025-07-01T12:00:00Z');
      expect(result).toContain('2025');
      expect(result).toContain('Jul');
    });
  });

  describe('formatRelativeTime', () => {
    const now = new Date('2026-07-15T12:00:00Z').getTime();

    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(now);
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('returns empty string for empty or invalid timestamps', () => {
      expect(formatRelativeTime('')).toBe('');
      expect(formatRelativeTime('not-a-date')).toBe('');
    });

    it.each([
      ['2026-07-15T11:59:59Z', 'just now'],
      ['2026-07-15T11:59:55Z', '5s ago'],
      ['2026-07-15T11:59:00Z', '1m ago'],
      ['2026-07-15T11:00:00Z', '1h ago'],
      ['2026-07-14T12:00:00Z', '1d ago'],
      ['2026-07-15T12:00:04Z', 'just now'],
      ['2026-07-15T12:00:55Z', 'in 55s'],
      ['2026-07-15T12:01:00Z', 'in 1m'],
      ['2026-07-15T13:00:00Z', 'in 1h'],
      ['2026-07-16T12:00:00Z', 'in 1d'],
    ])('formats %s as "%s"', (timestamp, expected) => {
      expect(formatRelativeTime(timestamp)).toBe(expected);
    });

    it('falls back to short date for timestamps older than 30 days', () => {
      const formatted = formatRelativeTime('2026-06-01T12:00:00Z');
      expect(formatted).toContain('Jun');
      expect(formatted).toContain('1');
    });
  });
});
