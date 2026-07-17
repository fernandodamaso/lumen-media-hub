import { AutomationSummary, summarizeAutomationHealth } from './automation.models';

describe('automation.models', () => {
  it('summarizes overall health as worst service status and counts actionable problems', () => {
    const summary: AutomationSummary = {
      generatedAt: '',
      services: [
        { id: 'a', name: 'A', status: 'healthy', detail: '' },
        { id: 'b', name: 'B', status: 'down', detail: '' },
        { id: 'c', name: 'C', status: 'degraded', detail: '' },
      ],
      preview: [],
      problems: [
        { id: 'p1', summary: '', serviceId: null, severity: 'actionable' },
        { id: 'p2', summary: '', serviceId: null, severity: 'actionable' },
        { id: 'p3', summary: '', serviceId: null, severity: 'warning' },
      ],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    };
    expect(summarizeAutomationHealth(summary)).toEqual({ overall: 'down', actionableCount: 2 });
  });

  it('summarizes empty services as unknown with zero actionables', () => {
    const summary: AutomationSummary = {
      generatedAt: '',
      services: [],
      preview: [],
      problems: [],
      availability: { services: 'empty', preview: 'empty', problems: 'empty' },
    };
    expect(summarizeAutomationHealth(summary)).toEqual({ overall: 'unknown', actionableCount: 0 });
  });
});
