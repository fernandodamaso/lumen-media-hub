import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal, WritableSignal } from '@angular/core';
import { vi } from 'vitest';
import { AutomationBoard } from './automation-board';
import { AutomationFacade, AutomationStatus } from './automation.facade';
import { AutomationSummary } from './automation.models';
import { CronRun } from '../reports/reports.models';

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
    expect(fixture.nativeElement.querySelectorAll('.compact-row--skeleton').length).toBeGreaterThan(0);

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

  it('renders the compact Automation System header', () => {
    facade.status.set('ready');
    facade.summary.set({
      generatedAt: '',
      services: [],
      preview: [],
      problems: [],
      availability: { services: 'empty', preview: 'empty', problems: 'empty' },
    });
    fixture.detectChanges();

    const heading = fixture.nativeElement.querySelector('h2');
    expect(heading?.textContent).toContain('Automation System');
    expect(heading?.querySelector('svg')).toBeTruthy();
  });

  it('renders connected services sorted with unhealthy first', () => {
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

    const rows = fixture.nativeElement.querySelectorAll('.card-section:nth-of-type(1) .compact-row');
    expect(rows[0].textContent).toContain('SABnzbd');
    expect(rows[0].textContent).toContain('Down');
    expect(rows[1].textContent).toContain('Radarr');
    expect(rows[1].textContent).toContain('Healthy');
    expect(rows[0].querySelector('.service-status__dot')).toBeTruthy();
  });

  it('renders scheduled tasks with relative timestamps', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-15T12:00:00Z'));

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
        timestamp: '2026-07-15T11:00:00Z',
        status: 'Success',
        triage: 'quiet',
        detail: '',
        fatal: null,
        applied: null,
        exitCode: 0,
      },
    ]);
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('.card-section:nth-of-type(2) .compact-row');
    expect(rows[0].textContent).toContain('Refresh the complete media library index');
    expect(rows[0].querySelector('.compact-time')?.textContent).toContain('1h ago');

    vi.useRealTimers();
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
  });

  it('shows the last summary timestamp in the footer', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-15T12:00:00Z'));

    facade.status.set('ready');
    facade.summary.set({
      generatedAt: '2026-07-15T11:55:00Z',
      services: [],
      preview: [],
      problems: [],
      availability: { services: 'empty', preview: 'empty', problems: 'empty' },
    });
    fixture.detectChanges();

    const footer = fixture.nativeElement.querySelector('.mm-card__footer');
    expect(footer?.textContent).toContain('Last summary');
    expect(footer?.textContent).toContain('5m ago');

    vi.useRealTimers();
  });

  it('renders items with missing IDs without duplicate tracking errors', () => {
    facade.status.set('ready');
    facade.summary.set({
      generatedAt: '',
      services: [
        { id: '', name: 'Service A', status: 'healthy', detail: '' },
        { id: '', name: 'Service B', status: 'healthy', detail: '' },
      ],
      preview: [],
      problems: [],
      availability: { services: 'present', preview: 'empty', problems: 'empty' },
    });
    facade.tasks.set([
      { id: '', jobId: '', jobTitle: 'Task A', schedule: '', timestamp: '', status: '', triage: 'quiet', detail: '', fatal: null, applied: null, exitCode: 0 },
      { id: '', jobId: '', jobTitle: 'Task B', schedule: '', timestamp: '', status: '', triage: 'quiet', detail: '', fatal: null, applied: null, exitCode: 0 },
    ]);
    expect(() => fixture.detectChanges()).not.toThrow();
    expect(fixture.nativeElement.querySelectorAll('.compact-row').length).toBe(4);
  });

  it('uses compact list styles and container query for narrow cards', () => {
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
    expect(styles).toContain('.compact-list');
    expect(styles).toContain('.compact-row');
    expect(styles).toContain('.automation-body');
    expect(styles).toContain('grid-template-columns: repeat(2, minmax(0, 1fr))');
    expect(styles).toContain('@container (max-width: 720px)');
    expect(styles).not.toContain('.tile-grid');
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
