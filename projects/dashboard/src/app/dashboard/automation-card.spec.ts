import { ComponentFixture, TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { AutomationSummary, summarizeAutomationHealth } from '../automation/automation.models';
import { ServiceHealthFacade, ServiceHealthStatus } from '../automation/service-health.facade';
import { StorageFacade, StorageStatus } from '../storage/storage.facade';
import { StorageOverview } from '../storage/storage.models';
import { AutomationCard } from './automation-card';

describe('AutomationCard', () => {
  let fixture: ComponentFixture<AutomationCard>;
  let health: ReturnType<typeof createHealth>;
  let storage: ReturnType<typeof createStorage>;
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
      this.open = true;
    });
    HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
      this.open = false;
      this.dispatchEvent(new Event('close'));
    });

    health = createHealth();
    storage = createStorage();
    TestBed.configureTestingModule({
      imports: [AutomationCard],
      providers: [
        provideRouter([]),
        { provide: ServiceHealthFacade, useValue: health },
        { provide: StorageFacade, useValue: storage },
      ],
    });
    fixture = TestBed.createComponent(AutomationCard);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders connected services and storage footer', () => {
    seedHealthyOnly();
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('#automation-heading')?.textContent).toContain('Connected services');
    expect(root.textContent).toContain('Sonarr');
    expect(root.textContent).not.toContain('Recent runs');
    expect(root.textContent).toContain('Media library');
    expect(root.textContent).toContain('View reports');
  });

  it('keeps an all-healthy list flat without a fold', () => {
    seedHealthyOnly();
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.healthy-fold')).toBeNull();
    expect(root.querySelector('.svc--flagged')).toBeNull();
    expect(root.textContent).toContain('Sonarr');
    expect(root.textContent).toContain('Radarr');
  });

  it('pins flagged services above the healthy fold, worst first', () => {
    seedMixedHealth();
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const flagged = [...root.querySelectorAll('.svc--flagged .svc__name')].map((el) =>
      el.textContent.trim(),
    );
    expect(flagged).toEqual(['SABnzbd', 'Prowlarr']);
    expect(root.querySelector('.healthy-fold summary')?.textContent).toMatch(/2 healthy/);
    expect(root.querySelector('.healthy-fold')?.textContent).toContain('Sonarr');
    expect(root.querySelector('.healthy-fold')?.textContent).toContain('Radarr');
    expect(root.querySelector('.svc__trigger')?.getAttribute('aria-controls')).toBe(
      root.querySelector('dialog')?.id,
    );
  });

  it('opens the dialog with only the clicked service problems', () => {
    seedMixedHealth();
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const prowlarr = [...root.querySelectorAll<HTMLButtonElement>('.svc__trigger')].find((btn) =>
      btn.textContent.includes('Prowlarr'),
    );
    prowlarr?.click();

    const dialog = root.querySelector('dialog');
    expect(dialog?.open).toBe(true);
    expect(dialog?.textContent).toContain('Prowlarr');
    expect(dialog?.textContent).toContain('Prowlarr indexer response slow');
    expect(dialog?.textContent).toContain('Prowlarr indexer in cooldown');
    expect(dialog?.textContent).not.toContain('SABnzbd unreachable');
  });

  it('shows empty-state copy when a flagged service has no problems', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'sabnzbd', name: 'SABnzbd', status: 'down', detail: 'Unreachable', latencyMs: null },
        { id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: '', latencyMs: 12 },
      ],
      problems: [],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'empty' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    expect(fixtureHost(fixture).querySelector('dialog')?.textContent).toContain(
      'No specific problems reported',
    );
  });

  it('lists missing episode rows under an aggregate Sonarr problem', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'degraded', detail: '33 missing', latencyMs: 20 },
      ],
      problems: [
        {
          id: 'sonarr-missing',
          summary: '33 Sonarr episode(s) missing',
          serviceId: 'sonarr',
          severity: 'warning',
          items: [
            { title: 'Show S01E01', when: 'Tonight' },
            { title: 'Show S01E02', when: 'Tomorrow' },
          ],
          itemCount: 33,
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    const dialogText = fixtureHost(fixture).querySelector('dialog')?.textContent ?? '';
    expect(dialogText).toContain('Show S01E01');
    expect(dialogText).toContain('Show S01E02');
    expect(dialogText).toContain('and 31 more not shown');
  });

  it('groups dialog problems actionable before warning', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'prowlarr', name: 'Prowlarr', status: 'degraded', detail: 'Indexer lag', latencyMs: 40 },
      ],
      problems: [
        {
          id: 'problem-w',
          summary: 'Prowlarr indexer in cooldown',
          serviceId: 'prowlarr',
          severity: 'warning',
        },
        {
          id: 'problem-a',
          summary: 'Prowlarr needs attention',
          serviceId: 'prowlarr',
          severity: 'actionable',
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    const text = fixtureHost(fixture).querySelector('dialog')?.textContent ?? '';
    expect(text.indexOf('Needs attention')).toBeGreaterThanOrEqual(0);
    expect(text.indexOf('Needs attention')).toBeLessThan(text.indexOf('Warning'));
    expect(text.indexOf('Prowlarr needs attention')).toBeLessThan(
      text.indexOf('Prowlarr indexer in cooldown'),
    );
  });

  it('clears the selected service when the dialog closes', () => {
    seedMixedHealth();
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    root.querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    expect(fixture.componentInstance.selectedService()?.id).toBe('sabnzbd');

    root.querySelector<HTMLButtonElement>('.mm-dialog__close')?.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.selectedService()).toBeNull();
  });

  function seedHealthyOnly(): void {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: '', latencyMs: 12 },
        { id: 'radarr', name: 'Radarr', status: 'healthy', detail: '', latencyMs: 10 },
      ],
      problems: [],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'empty' },
    });
    seedStorage();
  }

  function seedMixedHealth(): void {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: '', latencyMs: 12 },
        { id: 'radarr', name: 'Radarr', status: 'healthy', detail: '', latencyMs: 10 },
        { id: 'prowlarr', name: 'Prowlarr', status: 'degraded', detail: 'Indexer lag', latencyMs: 40 },
        { id: 'sabnzbd', name: 'SABnzbd', status: 'down', detail: 'Unreachable', latencyMs: null },
      ],
      problems: [
        { id: 'problem-1', summary: 'SABnzbd unreachable', serviceId: 'sabnzbd', severity: 'actionable' },
        {
          id: 'problem-2',
          summary: 'Prowlarr indexer response slow',
          serviceId: 'prowlarr',
          severity: 'warning',
        },
        {
          id: 'problem-3',
          summary: 'Prowlarr indexer in cooldown',
          serviceId: 'prowlarr',
          severity: 'warning',
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
  }

  function seedStorage(): void {
    storage.status.set('ready');
    storage.overview.set({
      generatedAt: '',
      volumes: [
        {
          id: 'media',
          label: 'Media library',
          kind: 'library',
          usedBytes: 50,
          totalBytes: 100,
        },
      ],
    });
  }
});

function createHealth() {
  const summary = signal<AutomationSummary | null>(null);
  return {
    status: signal<ServiceHealthStatus>('loading'),
    summary,
    services: computed(() => summary()?.services ?? []),
    problems: computed(() => summary()?.problems ?? []),
    health: computed(() => {
      const current = summary();
      return current
        ? summarizeAutomationHealth(current)
        : { overall: 'unknown' as const, actionableCount: 0 };
    }),
    error: signal(''),
    startPolling: vi.fn(),
    refresh: vi.fn(),
  };
}

function createStorage() {
  const overview = signal<StorageOverview | null>(null);
  return {
    status: signal<StorageStatus>('loading'),
    overview,
    volumes: computed(() => overview()?.volumes ?? []),
    error: signal(''),
    startPolling: vi.fn(),
    refresh: vi.fn(),
  };
}

