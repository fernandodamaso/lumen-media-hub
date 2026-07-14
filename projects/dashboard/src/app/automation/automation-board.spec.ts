import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal, WritableSignal } from '@angular/core';
import { vi } from 'vitest';
import { AutomationBoard } from './automation-board';
import { AutomationFacade, AutomationStatus } from './automation.facade';
import { AutomationSummary, CronRun } from '../media-stack/media-stack-api';

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
    expect(fixture.nativeElement.querySelectorAll('.tile-grid--skeleton').length).toBeGreaterThan(0);

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

    const flatRows = fixture.nativeElement.querySelectorAll('.flat-row');
    expect(flatRows[0].textContent).toContain('SABnzbd');
    expect(flatRows[0].textContent).toContain('Down');
    expect(flatRows[1].textContent).toContain('Radarr');
    expect(flatRows[1].textContent).toContain('Healthy');
    expect(fixture.nativeElement.querySelector('.mm-status--danger')?.textContent).toContain('Down');
  });

  it('uses a two-column card layout that stacks only from its container width', () => {
    facade.status.set('ready');
    facade.summary.set({
      generatedAt: '',
      services: [],
      preview: [],
      problems: [],
      availability: { services: 'empty', preview: 'empty', problems: 'empty' },
    });
    fixture.detectChanges();
    const styles = componentStyles();
    expect(fixture.nativeElement.querySelector('h2')?.textContent).toContain('Automation');
    expect(fixture.nativeElement.querySelector('h3')?.textContent).toContain('Services');
    expect(fixture.nativeElement.querySelectorAll('h3')[1]?.textContent).toContain('Up Next Scheduled Tasks');
    expect(styles).toContain('grid-template-columns: repeat(2, minmax(0, 1fr))');
    expect(styles).toContain('grid-column: 1/-1');
    expect(styles).toContain('@container (max-width: 520px)');
    expect(styles).toMatch(/@container \(max-width: 520px\)[\s\S]*\.tile-grid[\s\S]*grid-template-columns:\s*1fr/);
    expect(styles).not.toContain('@media (max-width: 950px)');
    expect(styles).toContain('background: var(--mm-component-raised-bg)');
  });

  it('keeps scheduled task metadata intact and allows titles to wrap without clipping', () => {
    facade.status.set('ready');
    facade.summary.set({
      generatedAt: '',
      services: [],
      preview: [],
      problems: [],
      availability: { services: 'empty', preview: 'empty', problems: 'empty' },
    });
    facade.tasks.set([
      {
        id: 'task-1',
        jobId: 'refresh-library',
        jobTitle: 'Refresh the complete media library index',
        schedule: '0 */6 * * *',
        timestamp: '2026-07-14T18:30:00Z',
        status: 'Success',
        triage: 'quiet',
        detail: '',
        fatal: null,
        applied: null,
        exitCode: 0,
      },
    ]);
    fixture.detectChanges();

    const task = fixture.nativeElement.querySelector('.preview-row');
    expect(task.textContent).toContain('Refresh the complete media library index');
    expect(task.querySelector('.task-schedule')?.textContent).toContain('0 */6 * * *');
    expect(task.querySelector('.task-timestamp')?.textContent).toContain('Jul 14');
    expect(task.textContent).toContain('Success');

    const styles = componentStyles();
    expect(styles).not.toContain('text-overflow: ellipsis');
    expect(styles).toContain('.task-schedule');
    expect(styles).toContain('.task-timestamp');
    expect(styles).toContain('white-space: nowrap');
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

    const flatRows = fixture.nativeElement.querySelectorAll('.flat-row');
    expect(flatRows[0].textContent).toContain('Service down');
    expect(flatRows[0].textContent).toContain('Needs attention');
    expect(flatRows[1].textContent).toContain('Slow indexer');
    expect(flatRows[1].textContent).toContain('Warning');
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
    expect(fixture.nativeElement.querySelectorAll('.flat-row').length).toBe(4);
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
