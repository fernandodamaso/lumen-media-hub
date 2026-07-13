import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { CronHealthSummary, CronRun } from '../downloads/media-stack-api';
import { ReportsFacade, ReportsStatus } from './reports.facade';
import { ReportsPage } from './reports-page';

describe('ReportsPage', () => {
  let fixture: ComponentFixture<ReportsPage>;
  let facade: ReturnType<typeof createFacade>;

  beforeEach(() => {
    facade = createFacade();
    TestBed.configureTestingModule({
      imports: [ReportsPage],
      providers: [{ provide: ReportsFacade, useValue: facade }],
    });
    // Override component-level providers so the mock facade wins.
    TestBed.overrideComponent(ReportsPage, {
      set: { providers: [{ provide: ReportsFacade, useValue: facade }] },
    });
    fixture = TestBed.createComponent(ReportsPage);
  });

  it('renders loading, empty, and hard-error states', () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Loading reports');

    facade.status.set('empty');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No cron history yet');

    facade.status.set('error');
    facade.error.set('Offline');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Offline');
    expect(fixture.nativeElement.textContent).toContain('Reports unavailable');
    expect(fixture.nativeElement.querySelector('.mm-state-card--danger')).toBeTruthy();
  });

  it('prioritizes actionable runs and keeps quiet runs collapsed', () => {
    facade.status.set('mixed');
    facade.summary.set({ kind: 'mixed', total: 3, actionable: 1, quiet: 2 });
    facade.generatedAt.set('2026-07-12T12:00:00Z');
    facade.runs.set([
      makeRun({ id: 'fatal-1', jobTitle: 'Watchdog', status: 'fatal', triage: 'actionable', detail: 'Disk full', fatal: 'Disk full' }),
      makeRun({ id: 'quiet-1', jobTitle: 'Weekly validate', status: 'ok', triage: 'quiet', detail: 'Completed' }),
      makeRun({ id: 'quiet-2', jobTitle: 'Hardlink cleanup', status: 'ok', triage: 'quiet', detail: 'Nothing to check' }),
    ]);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('actionable run');
    expect(text).toContain('Watchdog');
    expect(text).toContain('2 quiet runs');

    const actionableList = fixture.nativeElement.querySelector('[aria-label="Actionable runs"]');
    const quietSection = fixture.nativeElement.querySelector('.quiet-section') as HTMLDetailsElement;
    expect(actionableList?.textContent).toContain('Watchdog');
    expect(quietSection.open).toBe(false);

    const firstActionable = actionableList?.querySelector('.run') as HTMLElement;
    expect(firstActionable?.textContent).toContain('Watchdog');
  });

  it('expands run detail via native details element', () => {
    facade.status.set('mixed');
    facade.summary.set({ kind: 'mixed', total: 1, actionable: 1, quiet: 0 });
    facade.runs.set([
      makeRun({ id: 'fatal-1', jobTitle: 'Watchdog', status: 'fatal', triage: 'actionable', detail: 'Disk full', fatal: 'Disk full' }),
    ]);
    fixture.detectChanges();

    const details = fixture.nativeElement.querySelector('.run-list .run') as HTMLDetailsElement;
    expect(details.open).toBe(false);
    details.open = true;
    fixture.detectChanges();
    expect(details.open).toBe(true);
    expect(details.querySelector('.run-detail')?.textContent).toContain('Disk full');
  });

  it('shows calm all-clear messaging without a danger state card', () => {
    facade.status.set('allClear');
    facade.summary.set({ kind: 'allClear', total: 2, actionable: 0, quiet: 2 });
    facade.runs.set([
      makeRun({ id: 'quiet-1', jobTitle: 'Weekly validate', status: 'ok', triage: 'quiet', detail: 'Completed' }),
      makeRun({ id: 'quiet-2', jobTitle: 'Hardlink cleanup', status: 'ok', triage: 'quiet', detail: 'Nothing to check' }),
    ]);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('All clear');
    expect(fixture.nativeElement.querySelector('mm-state-card[tone="danger"]')).toBeNull();
    expect(text).not.toContain('Reports unavailable');
  });

  it('shows retained-data refresh error alongside the list', () => {
    facade.status.set('mixed');
    facade.summary.set({ kind: 'mixed', total: 1, actionable: 1, quiet: 0 });
    facade.error.set('Could not refresh reports. Showing last loaded history.');
    facade.runs.set([
      makeRun({ id: 'fatal-1', jobTitle: 'Watchdog', status: 'fatal', triage: 'actionable', detail: 'Disk full' }),
    ]);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Showing last loaded history');
    expect(fixture.nativeElement.textContent).toContain('Watchdog');
  });

  it('calls facade refresh from the Refresh button', async () => {
    facade.status.set('allClear');
    facade.summary.set({ kind: 'allClear', total: 1, actionable: 0, quiet: 1 });
    facade.generatedAt.set('2026-07-12T12:00:00Z');
    facade.runs.set([makeRun({ id: 'quiet-1', jobTitle: 'Weekly validate', status: 'ok', triage: 'quiet' })]);
    fixture.detectChanges();

    findButton('Refresh').click();
    await fixture.whenStable();
    expect(facade.refresh).toHaveBeenCalled();
  });
});

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
    runs: signal<CronRun[]>([]),
    summary: signal<CronHealthSummary>({ kind: 'empty', total: 0, actionable: 0, quiet: 0 }),
    generatedAt: signal(''),
    error: signal(''),
    refreshing: signal(false),
    load: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn().mockResolvedValue(undefined),
  };
}

function findButton(label: string): HTMLButtonElement {
  const buttons = Array.from(document.querySelectorAll('button')) as HTMLButtonElement[];
  const match = buttons.find((button) => button.textContent?.includes(label));
  if (!match) throw new Error(`Button not found: ${label}`);
  return match;
}
