import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { ActivatedRoute, convertToParamMap, ParamMap } from '@angular/router';
import { BehaviorSubject, of } from 'rxjs';
import { vi } from 'vitest';
import { AutomationProblem, AutomationService, QueueHygieneSummary } from '../automation/automation.models';
import { ServiceHealthFacade, ServiceHealthStatus } from '../automation/service-health.facade';
import { fixtureHost } from '../../testing/fixture-host';
import { CronHealthSummary, CronHistoricalRun, CronRun } from './reports.models';
import { ReportsFacade, ReportsStatus } from './reports.facade';
import { ReportsPage } from './reports-page';

describe('ReportsPage', () => {
  let fixture: ComponentFixture<ReportsPage>;
  let facade: ReturnType<typeof createFacade>;
  let health: ReturnType<typeof createHealthFacade>;
  let queryParams: BehaviorSubject<ParamMap>;

  beforeEach(() => {
    facade = createFacade();
    health = createHealthFacade();
    queryParams = new BehaviorSubject<ParamMap>(convertToParamMap({}));
    TestBed.configureTestingModule({
      imports: [ReportsPage],
      providers: [
        { provide: ReportsFacade, useValue: facade },
        { provide: ServiceHealthFacade, useValue: health },
        {
          provide: ActivatedRoute,
          useValue: {
            queryParamMap: queryParams.asObservable(),
            fragment: of(null),
          },
        },
      ],
    });
    TestBed.overrideComponent(ReportsPage, {
      set: { providers: [{ provide: ReportsFacade, useValue: facade }] },
    });
    fixture = TestBed.createComponent(ReportsPage);
  });

  it('renders loading, empty, and hard-error states for cron history', () => {
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('Loading reports');
    expect(root.textContent).toContain('Service health');

    facade.status.set('empty');
    fixture.detectChanges();
    expect(root.textContent).toContain('No cron history yet');

    facade.status.set('error');
    facade.error.set('Offline');
    fixture.detectChanges();
    expect(root.textContent).toContain('Offline');
    expect(root.textContent).toContain('Reports unavailable');
    expect(root.querySelector('.mm-state-card--danger')).toBeTruthy();
  });

  it('prioritizes actionable runs and keeps quiet runs collapsed', () => {
    facade.status.set('mixed');
    facade.summary.set({ kind: 'mixed', totalJobs: 3, affectedJobs: 1, healthyJobs: 2 });
    facade.generatedAt.set('2026-07-12T12:00:00Z');
    facade.currentRuns.set([
      makeRun({ id: 'fatal-1', jobTitle: 'Watchdog', status: 'fatal', triage: 'actionable', detail: 'Disk full', fatal: 'Disk full' }),
      makeRun({ id: 'quiet-1', jobTitle: 'Weekly validate', status: 'ok', triage: 'quiet', detail: 'Completed' }),
      makeRun({ id: 'quiet-2', jobTitle: 'Hardlink cleanup', status: 'ok', triage: 'quiet', detail: 'Nothing to check' }),
    ]);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const text = root.textContent;
    expect(text).toContain('need attention');
    expect(text).toContain('Watchdog');
    expect(text).toContain('2 healthy jobs');

    const actionableList = root.querySelector('[aria-label="Actionable runs"]');
    const quietSection = root.querySelector('.quiet-section') as HTMLDetailsElement;
    expect(actionableList?.textContent).toContain('Watchdog');
    expect(quietSection.open).toBe(false);

    const firstActionable = actionableList?.querySelector('.run') as HTMLElement | null;
    expect(firstActionable?.textContent).toContain('Watchdog');
  });

  it('shows older failures in a collapsed History section with Resolved labels', () => {
    facade.status.set('allClear');
    facade.summary.set({ kind: 'allClear', totalJobs: 1, affectedJobs: 0, healthyJobs: 1 });
    facade.currentRuns.set([
      makeRun({ id: 'ok-1', jobTitle: 'Watchdog', status: 'ok', triage: 'quiet', detail: 'All services are healthy' }),
    ]);
    facade.historyRuns.set([
      { ...makeRun({ id: 'h-fatal', jobTitle: 'Watchdog', status: 'fatal', triage: 'actionable', detail: 'Disk full', fatal: 'Disk full' }), resolved: true },
      { ...makeRun({ id: 'h-unresolved', jobTitle: 'Stale metadata', status: 'fatal', triage: 'actionable', detail: 'Stuck', fatal: 'Stuck' }), resolved: false },
    ]);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const historySection = root.querySelector('.history-section') as HTMLDetailsElement;
    expect(historySection).toBeTruthy();
    expect(historySection.open).toBe(false);
    const historyText = historySection.textContent;
    expect(historyText).toContain('History (2 runs)');
    expect(historyText).toContain('Disk full');
    expect(historyText).toContain('Resolved');
    expect(historyText).toContain('Historical');
  });

  it('expands run detail via native details element', () => {
    facade.status.set('mixed');
    facade.summary.set({ kind: 'mixed', totalJobs: 1, affectedJobs: 1, healthyJobs: 0 });
    facade.currentRuns.set([
      makeRun({ id: 'fatal-1', jobTitle: 'Watchdog', status: 'fatal', triage: 'actionable', detail: 'Disk full', fatal: 'Disk full' }),
    ]);
    fixture.detectChanges();

    const details = fixtureHost(fixture).querySelector('.run-list .run') as HTMLDetailsElement;
    const summary = details.querySelector('summary') as HTMLElement;
    expect(details.open).toBe(false);

    summary.click();
    fixture.detectChanges();
    expect(details.open).toBe(true);
    expect(details.querySelector('.run-detail')?.textContent).toContain('Disk full');

    summary.click();
    fixture.detectChanges();
    expect(details.open).toBe(false);
  });

  it('shows calm all-clear messaging without a danger state card', () => {
    facade.status.set('allClear');
    facade.summary.set({ kind: 'allClear', totalJobs: 2, affectedJobs: 0, healthyJobs: 2 });
    facade.currentRuns.set([
      makeRun({ id: 'quiet-1', jobTitle: 'Weekly validate', status: 'ok', triage: 'quiet', detail: 'Completed' }),
      makeRun({ id: 'quiet-2', jobTitle: 'Hardlink cleanup', status: 'ok', triage: 'quiet', detail: 'Nothing to check' }),
    ]);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const text = root.textContent;
    expect(text).toContain('All clear');
    expect(root.querySelector('mm-state-card[tone="danger"]')).toBeNull();
    expect(text).not.toContain('Reports unavailable');
  });

  it('shows retained-data refresh error alongside the list', () => {
    facade.status.set('mixed');
    facade.summary.set({ kind: 'mixed', totalJobs: 1, affectedJobs: 1, healthyJobs: 0 });
    facade.error.set('Could not refresh reports. Showing last loaded history.');
    facade.currentRuns.set([
      makeRun({ id: 'fatal-1', jobTitle: 'Watchdog', status: 'fatal', triage: 'actionable', detail: 'Disk full' }),
    ]);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('Showing last loaded history');
    expect(root.textContent).toContain('Watchdog');
  });

  it('calls both facades from the Refresh button', async () => {
    facade.status.set('allClear');
    facade.summary.set({ kind: 'allClear', totalJobs: 1, affectedJobs: 0, healthyJobs: 1 });
    facade.generatedAt.set('2026-07-12T12:00:00Z');
    facade.currentRuns.set([makeRun({ id: 'quiet-1', jobTitle: 'Weekly validate', status: 'ok', triage: 'quiet' })]);
    fixture.detectChanges();

    findButton('Refresh').click();
    await fixture.whenStable();
    expect(facade.refresh).toHaveBeenCalled();
    expect(health.refresh).toHaveBeenCalled();
  });

  it('reacts to service query parameter changes without recreating the page', () => {
    health.services.set([
      { id: 'prowlarr', name: 'Prowlarr', status: 'degraded', detail: '1 indexer disabled', latencyMs: 350 },
      { id: 'sabnzbd', name: 'SABnzbd', status: 'down', detail: 'Last seen 18m ago' },
    ]);
    health.problems.set([
      { id: 'p1', summary: 'SABnzbd unreachable', serviceId: 'sabnzbd', severity: 'actionable' },
      { id: 'p2', summary: '1 indexer(s) disabled', serviceId: 'prowlarr', severity: 'warning' },
    ]);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('Prowlarr');
    expect(root.textContent).toContain('SABnzbd');

    queryParams.next(convertToParamMap({ service: 'prowlarr' }));
    fixture.detectChanges();
    expect(root.textContent).toContain('1 indexer(s) disabled');
    expect(root.textContent).not.toContain('SABnzbd unreachable');
  });

  it('shows healthy recovery for a selected service', () => {
    health.services.set([
      { id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK', latencyMs: 20 },
    ]);
    health.problems.set([
      { id: 'p3', summary: '4 Sonarr episode(s) missing', serviceId: 'sonarr', severity: 'warning' },
    ]);
    queryParams.next(convertToParamMap({ service: 'sonarr' }));
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('Sonarr');
    expect(root.textContent).toContain('No current live issues.');
    expect(root.textContent).not.toContain('4 Sonarr episode(s) missing');
  });

  it('falls back to active issues for invalid service ids', () => {
    health.services.set([
      { id: 'prowlarr', name: 'Prowlarr', status: 'degraded', detail: '1 indexer disabled', latencyMs: 350 },
    ]);
    health.problems.set([
      { id: 'p2', summary: '1 indexer(s) disabled', serviceId: 'prowlarr', severity: 'warning' },
    ]);
    queryParams.next(convertToParamMap({ service: 'missing-service' }));
    fixture.detectChanges();

    expect(fixtureHost(fixture).textContent).toContain('Unknown service. Showing all current issues.');
    expect(fixtureHost(fixture).textContent).toContain('1 indexer(s) disabled');
  });

  it('keeps cron history visible while service health is loading or unavailable', () => {
    health.status.set('loading');
    facade.status.set('mixed');
    facade.summary.set({ kind: 'mixed', totalJobs: 1, affectedJobs: 1, healthyJobs: 0 });
    facade.currentRuns.set([
      makeRun({ id: 'fatal-1', jobTitle: 'Watchdog', status: 'fatal', triage: 'actionable', detail: 'Disk full' }),
    ]);
    fixture.detectChanges();

    let root = fixtureHost(fixture);
    expect(root.textContent).toContain('Loading service health');
    expect(root.textContent).toContain('Watchdog');

    health.status.set('error');
    health.error.set('Service health is temporarily unavailable. Try again.');
    fixture.detectChanges();
    root = fixtureHost(fixture);
    expect(root.textContent).toContain('Service health unavailable');
    expect(root.textContent).toContain('Watchdog');
  });

  it('disables Refresh while either facade is refreshing', () => {
    health.refreshing.set(true);
    fixture.detectChanges();
    expect(findButton('Refresh').disabled).toBe(true);
  });

  it('renders eligible observe candidates and previews without enabling cleanup on its own', () => {
    health.queueHygiene.set(makeQueueHygiene());
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('1 stale import detected');
    expect(root.textContent).toContain('Automatic cleanup is observing only.');
    expect(root.textContent).toContain('Not an upgrade for existing episode file(s).');
    expect(findButton('Run safe cleanup').disabled).toBe(false);

    findButton('Preview now').click();
    expect(health.runQueueHygiene).toHaveBeenCalledWith('observe');
  });

  it('requires confirmation before auto cleanup and disables it when the circuit is open', () => {
    health.queueHygiene.set(makeQueueHygiene());
    fixture.detectChanges();
    findButton('Run safe cleanup').click();
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('does not remove qBittorrent torrents or downloaded files');
    expect(health.runQueueHygiene).not.toHaveBeenCalledWith('auto');

    health.queueHygiene.set({ ...makeQueueHygiene(), circuitOpen: true });
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('Automatic cleanup paused');
    expect(findButton('Run safe cleanup').disabled).toBe(true);
  });
});

function makeQueueHygiene(): QueueHygieneSummary {
  return {
    mode: 'observe',
    circuitOpen: false,
    eligibleCount: 1,
    blockedCount: 0,
    eligibleItems: [{
      downloadId: 'a'.repeat(40),
      queueIds: [101],
      titles: ['Demo Show S01E02'],
      reason: 'Not an upgrade for existing episode file(s).',
      completedAt: '2026-08-23T08:00:00Z',
      ageHours: 4.5,
    }],
    blockedItems: [],
    lastCycleAt: '2026-08-23T12:30:00Z',
    lastCleanup: null,
    verification: null,
  };
}

function makeRun(partial: Partial<CronRun> & Pick<CronRun, 'id' | 'jobTitle' | 'status' | 'triage'>): CronRun {
  return {
    jobId: partial.jobId ?? partial.id,
    timestamp: partial.timestamp ?? '2026-07-12T12:00:00Z',
    detail: partial.detail ?? '',
    fatal: partial.fatal ?? null,
    applied: partial.applied ?? null,
    exitCode: partial.exitCode ?? null,
    ...partial,
  };
}

function createFacade() {
  return {
    status: signal<ReportsStatus>('loading'),
    currentRuns: signal<CronRun[]>([]),
    historyRuns: signal<CronHistoricalRun[]>([]),
    summary: signal<CronHealthSummary>({ kind: 'empty', totalJobs: 0, affectedJobs: 0, healthyJobs: 0 }),
    generatedAt: signal(''),
    error: signal(''),
    refreshing: signal(false),
    load: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn().mockResolvedValue(undefined),
  };
}

function createHealthFacade() {
  return {
    status: signal<ServiceHealthStatus>('ready'),
    services: signal<AutomationService[]>([]),
    problems: signal<AutomationProblem[]>([]),
    error: signal(''),
    refreshing: signal(false),
    queueHygiene: signal<QueueHygieneSummary | null>(null),
    queueHygieneRunning: signal(false),
    queueHygieneError: signal(''),
    lastQueueHygieneRun: signal(null),
    refresh: vi.fn().mockResolvedValue(undefined),
    runQueueHygiene: vi.fn().mockResolvedValue({ status: 'observed' }),
  };
}

function findButton(label: string): HTMLButtonElement {
  const buttons = Array.from(document.querySelectorAll('button'));
  const match = buttons.find((button) => button.textContent.includes(label));
  if (!match) throw new Error(`Button not found: ${label}`);
  return match;
}
