import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal, WritableSignal } from '@angular/core';
import { vi } from 'vitest';
import { AutomationBoard } from './automation-board';
import { AutomationFacade, AutomationStatus } from './automation.facade';
import { AutomationSummary, CronRun } from '../downloads/media-stack-api';

interface MockAutomationFacade {
  status: WritableSignal<AutomationStatus>;
  summary: WritableSignal<AutomationSummary | null>;
  error: WritableSignal<string>;
  tasks: WritableSignal<CronRun[]>;
  summaryUnavailable: WritableSignal<boolean>;
  tasksUnavailable: WritableSignal<boolean>;
  startPolling: () => void;
  refresh: () => Promise<void>;
}

describe('AutomationBoard', () => {
  let fixture: ComponentFixture<AutomationBoard>;
  let facade: MockAutomationFacade;

  beforeEach(() => {
    facade = createFacade();
    TestBed.configureTestingModule({
      imports: [AutomationBoard],
      providers: [{ provide: AutomationFacade, useValue: facade }],
    });
    fixture = TestBed.createComponent(AutomationBoard);
  });

  it('renders loading, empty, and error states with retry recovery', async () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Loading automation');

    facade.status.set('empty');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No automation data');

    facade.status.set('error');
    facade.error.set('Offline');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Offline');
    findButton('Try again').click();
    await fixture.whenStable();
    expect(facade.refresh).toHaveBeenCalled();
    expect(facade.status()).toBe('ready');
  });

  it('renders ready tiles with unhealthy services sorted first and semantic labels', () => {
    facade.status.set('ready');
    facade.summary.set({
      generatedAt: '2026-07-12T18:00:00Z',
      services: [
        { id: 'radarr', name: 'Radarr', status: 'healthy', detail: 'OK' },
        { id: 'sabnzbd', name: 'SABnzbd', status: 'down', detail: 'Connection refused' },
      ],
      preview: [{ id: 'p1', title: 'Dune', when: 'Jul 13', kind: 'movie' }],
      problems: [],
      availability: { services: 'present', preview: 'present', problems: 'empty' },
    });
    fixture.detectChanges();

    const tileRows = fixture.nativeElement.querySelectorAll('.tile-row');
    expect(tileRows[0].textContent).toContain('SABnzbd');
    expect(tileRows[0].textContent).toContain('Down');
    expect(tileRows[1].textContent).toContain('Radarr');
    expect(tileRows[1].textContent).toContain('Healthy');
    expect(fixture.nativeElement.querySelector('.mm-status--danger')?.textContent).toContain('Down');
  });

  it('declares container-query compact layout for narrow dashboard tracks', () => {
    fixture.detectChanges();
    const styles = componentStyles();
    expect(styles).toContain('@container (max-width: 520px)');
    expect(styles).toMatch(/@container \(max-width: 520px\)[\s\S]*\.tile-grid[\s\S]*grid-template-columns:\s*1fr/);
  });

  it('renders a partial banner when scheduled tasks are unavailable', () => {
    facade.status.set('partial');
    facade.summary.set({
      generatedAt: '2026-07-12T18:00:00Z',
      services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK' }],
      preview: [],
      problems: [],
      availability: { services: 'present', preview: 'unavailable', problems: 'unavailable' },
    });
    facade.tasksUnavailable.set(true);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Scheduled tasks unavailable');
    expect(fixture.nativeElement.textContent).toContain('Problem list unavailable');
  });

  it('renders problems sorted by severity with text labels', () => {
    facade.status.set('ready');
    facade.summary.set({
      generatedAt: '',
      services: [],
      preview: [],
      problems: [
        { id: 'w1', summary: 'Slow indexer', serviceId: 'prowlarr', severity: 'warning' },
        { id: 'a1', summary: 'Service down', serviceId: 'sabnzbd', severity: 'actionable' },
      ],
      availability: { services: 'empty', preview: 'empty', problems: 'present' },
    });
    fixture.detectChanges();

    const tileRows = fixture.nativeElement.querySelectorAll('.tile-row');
    expect(tileRows[0].textContent).toContain('Service down');
    expect(tileRows[0].textContent).toContain('Needs attention');
    expect(tileRows[1].textContent).toContain('Slow indexer');
    expect(tileRows[1].textContent).toContain('Warning');
  });

  it('renders items with missing IDs without duplicate tracking errors', () => {
    facade.status.set('ready');
    facade.summary.set({
      generatedAt: '',
      services: [
        { id: '', name: 'Service A', status: 'healthy', detail: '' },
        { id: '', name: 'Service B', status: 'healthy', detail: '' },
      ],
      preview: [
        { id: '', title: 'Preview A', when: '', kind: '' },
        { id: '', title: 'Preview B', when: '', kind: '' },
      ],
      problems: [
        { id: '', summary: 'Problem A', serviceId: null, severity: 'info' },
        { id: '', summary: 'Problem B', serviceId: null, severity: 'info' },
      ],
      availability: { services: 'present', preview: 'present', problems: 'present' },
    });
    expect(() => fixture.detectChanges()).not.toThrow();
    expect(fixture.nativeElement.querySelectorAll('.tile-row').length).toBe(4);
  });

  function findButton(label: string): HTMLButtonElement {
    return (Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[]).find(
      (button) => button.textContent?.includes(label),
    ) as HTMLButtonElement;
  }
});

function createFacade() {
  const status = signal<AutomationStatus>('loading');
  const summary = signal<AutomationSummary | null>(null);
  const error = signal('');
  const tasks = signal<CronRun[]>([]);
  const refresh = vi.fn(async () => {
    status.set('ready');
  });
  return {
    status,
    summary,
    error,
    tasks,
    summaryUnavailable: signal(false),
    tasksUnavailable: signal(false),
    startPolling: vi.fn(),
    refresh,
  };
}

function componentStyles(): string {
  return Array.from(document.querySelectorAll('style'))
    .map((node) => node.textContent ?? '')
    .join('\n');
}
