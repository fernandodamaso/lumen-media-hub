import { ComponentFixture, TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { fixtureHost } from '../../../testing/fixture-host';
import { AutomationSummary, summarizeAutomationHealth } from '../../automation/automation.models';
import { ServiceHealthFacade, ServiceHealthStatus } from '../../automation/service-health.facade';
import { StorageFacade, StorageStatus } from '../../storage/storage.facade';
import { StorageOverview } from '../../storage/storage.models';
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

  it('renders Sonarr detail stats, section heading, no banner and no external-link icon', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'degraded', detail: '34 missing · 17 shows · 1 queued', latencyMs: 20 },
      ],
      problems: [],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    const root = fixtureHost(fixture);
    const stats = root.querySelectorAll('.stat');
    expect(stats).toHaveLength(3);
    expect(stats[0].textContent).toContain('34');
    expect(stats[0].textContent).toContain('Missing');
    expect(stats[0].classList).toContain('stat--lead');
    expect(stats[1].textContent).toContain('17');
    expect(stats[1].textContent).toContain('Shows');
    expect(stats[2].textContent).toContain('1');
    expect(stats[2].textContent).toContain('Queued');
    expect(root.textContent).toContain('Missing episodes');
    expect(root.querySelector('.svc-detail__banner')).toBeNull();
    expect(root.querySelector('[lucideExternalLink]')).toBeNull();
    expect(root.innerHTML).not.toContain('lucide-external-link');
  });

  it('groups two Sonarr items with same href into details.show-card with 2 episodes missing', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'degraded', detail: '2 missing · 1 shows · 0 queued', latencyMs: 20 },
      ],
      problems: [
        {
          id: 'sonarr-missing',
          summary: '2 episodes missing',
          serviceId: 'sonarr',
          severity: 'warning',
          items: [
            { title: 'Show A S01E01', when: '2026-03-24T20:00:00Z', href: 'https://sonarr/series/1', posterUrl: null },
            { title: 'Show A S01E02', when: '2026-03-25T20:00:00Z', href: 'https://sonarr/series/1', posterUrl: null },
          ],
          itemCount: 2,
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    const root = fixtureHost(fixture);
    const details = root.querySelector('details.show-card');
    expect(details).toBeTruthy();
    const detailsEl = details as HTMLDetailsElement;
    expect(detailsEl.querySelector('summary')?.textContent).toContain('Show A');
    expect(detailsEl.querySelector('.show-card__sub')?.textContent).toContain('2 episodes missing');

    // Expand and check episode links
    detailsEl.open = true;
    fixture.detectChanges();
    const eps = detailsEl.querySelectorAll('.show-card__eps a.ep');
    expect(eps).toHaveLength(2);
    expect(eps[0].textContent).toContain('Season 1');
    expect(eps[0].textContent).toContain('Episode 1');
    expect(eps[0].textContent).not.toContain('S01E01');
    expect(eps[1].textContent).toContain('Season 1');
    expect(eps[1].textContent).toContain('Episode 2');
    expect(eps[1].textContent).not.toContain('S01E02');
    expect(eps[0].textContent).toContain('Mar 24');
    expect(eps[1].textContent).toContain('Mar 25');
  });

  it('renders single Sonarr item as direct a.show-card with season-episode subtitle', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'degraded', detail: '1 missing · 1 shows · 0 queued', latencyMs: 20 },
      ],
      problems: [
        {
          id: 'sonarr-missing',
          summary: '1 episode missing',
          serviceId: 'sonarr',
          severity: 'warning',
          items: [
            { title: 'Show B S01E03', when: '2026-03-26T20:00:00Z', href: 'https://sonarr/series/2', posterUrl: 'http://example.com/poster.jpg' },
          ],
          itemCount: 1,
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    const root = fixtureHost(fixture);
    const anchor = root.querySelector('a.show-card');
    expect(anchor).toBeTruthy();
    expect(anchor?.getAttribute('href')).toBe('https://sonarr/series/2');
    expect(anchor?.getAttribute('target')).toBe('_blank');
    expect(anchor?.getAttribute('rel')).toBe('noreferrer');
    expect(anchor?.querySelector('.show-card__sub')?.textContent).toContain('Season 1 · Episode 3');
    expect(anchor?.querySelector('img')).toBeTruthy();
    expect(root.querySelector('details.show-card')).toBeNull();
  });

  it('renders poster fallback when posterUrl is null and on image error', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'degraded', detail: '1 missing · 1 shows · 0 queued', latencyMs: 20 },
      ],
      problems: [
        {
          id: 'sonarr-missing',
          summary: '1 episode missing',
          serviceId: 'sonarr',
          severity: 'warning',
          items: [
            { title: 'Series X S01E01', when: '2026-04-01T20:00:00Z', href: null, posterUrl: null },
          ],
          itemCount: 1,
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    const root = fixtureHost(fixture);
    // No posterUrl -> no img, fallback span present
    expect(root.querySelector('.show-card__poster img')).toBeNull();
    expect(root.querySelector('.show-card__poster-fallback')).toBeTruthy();

    // Now test img error: add posterUrl and trigger error
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'degraded', detail: '1 missing · 1 shows · 0 queued', latencyMs: 20 },
      ],
      problems: [
        {
          id: 'sonarr-missing',
          summary: '1 episode missing',
          serviceId: 'sonarr',
          severity: 'warning',
          items: [
            { title: 'Series X S01E01', when: '2026-04-01T20:00:00Z', href: null, posterUrl: 'http://example.com/bad.jpg' },
          ],
          itemCount: 1,
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    fixture.detectChanges();
    const img = root.querySelector<HTMLImageElement>('.show-card__poster img');
    expect(img).toBeTruthy();
    const imgEl = img as HTMLImageElement;
    expect(imgEl.style.display).not.toBe('none');

    // Simulate image error
    imgEl.dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(imgEl.style.display).toBe('none');
    expect(root.querySelector('.show-card__poster-fallback')).toBeTruthy();
  });

  it('renders Radarr with MISSING MOVIES heading, Movies stat, Missing movie subtitle, no details', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'radarr', name: 'Radarr', status: 'degraded', detail: '5 missing · 3 movies · 0 queued', latencyMs: 20 },
      ],
      problems: [
        {
          id: 'radarr-missing',
          summary: '5 movies missing',
          serviceId: 'radarr',
          severity: 'warning',
          items: [
            { title: 'Movie A', when: '2026-05-01T20:00:00Z', href: 'https://radarr/movie/1', posterUrl: null },
            { title: 'Movie B', when: '2026-05-02T20:00:00Z', href: null, posterUrl: null },
          ],
          itemCount: 5,
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('Missing movies');

    const stats = root.querySelectorAll('.stat');
    expect(stats).toHaveLength(3);
    expect(stats[1].textContent).toContain('Movies');

    const anchors = root.querySelectorAll('a.show-card');
    const statics = root.querySelectorAll('span.show-card--static');
    expect(anchors.length + statics.length).toBe(2);
    expect(anchors).toHaveLength(1);
    expect(statics).toHaveLength(1);
    expect(anchors[0].querySelector('.show-card__sub')?.textContent).toContain('Missing movie');
    expect(statics[0].querySelector('.show-card__sub')?.textContent).toContain('Missing movie');
    expect(root.querySelector('details.show-card')).toBeNull();
  });

  it('renders Radarr items sharing same href as separate direct cards, zero details', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'radarr', name: 'Radarr', status: 'degraded', detail: '2 missing · 2 movies · 0 queued', latencyMs: 20 },
      ],
      problems: [
        {
          id: 'radarr-missing',
          summary: '2 movies missing',
          serviceId: 'radarr',
          severity: 'warning',
          items: [
            { title: 'Movie X', when: '2026-06-01T20:00:00Z', href: 'https://radarr/movie/1', posterUrl: null },
            { title: 'Movie Y', when: '2026-06-02T20:00:00Z', href: 'https://radarr/movie/1', posterUrl: null },
          ],
          itemCount: 2,
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    const root = fixtureHost(fixture);
    const anchors = root.querySelectorAll('a.show-card');
    expect(anchors).toHaveLength(2);
    expect(root.querySelector('details.show-card')).toBeNull();
    expect(anchors[0].textContent).toContain('Movie X');
    expect(anchors[1].textContent).toContain('Movie Y');
  });

  it('renders episode without href as static span inside multi-episode details card', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'degraded', detail: '2 missing · 1 shows · 0 queued', latencyMs: 20 },
      ],
      problems: [
        {
          id: 'sonarr-missing',
          summary: '2 episodes missing',
          serviceId: 'sonarr',
          severity: 'warning',
          items: [
            { title: 'Show A S01E01', when: '2026-03-24T20:00:00Z', href: 'https://sonarr/series/1', posterUrl: null },
            { title: 'Show A S01E02', when: '2026-03-25T20:00:00Z', href: null, posterUrl: null },
          ],
          itemCount: 2,
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    const root = fixtureHost(fixture);
    const details = root.querySelector('details.show-card');
    expect(details).toBeTruthy();
    const detailsEl = details as HTMLDetailsElement;
    detailsEl.open = true;
    fixture.detectChanges();

    const anchors = detailsEl.querySelectorAll('.show-card__eps a.ep');
    expect(anchors).toHaveLength(1);
    expect(anchors[0].getAttribute('href')).toBe('https://sonarr/series/1');
    expect(anchors[0].getAttribute('target')).toBe('_blank');

    const statics = detailsEl.querySelectorAll('.show-card__eps span.ep--static');
    expect(statics).toHaveLength(1);
    expect(statics[0].textContent).toContain('Episode 2');
    expect(statics[0].textContent).toContain('Mar 25');

    // No fake # links anywhere
    expect(root.innerHTML).not.toContain('href="#"');
    expect(root.innerHTML).not.toContain('href=&quot;#&quot;');
  });

  it('renders duplicate-title episodes without Angular duplicate-key error', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'degraded', detail: '2 missing · 1 shows · 0 queued', latencyMs: 20 },
      ],
      problems: [
        {
          id: 'sonarr-missing',
          summary: '2 episodes missing',
          serviceId: 'sonarr',
          severity: 'warning',
          items: [
            { title: 'Show A S01E01', when: '2026-03-24T20:00:00Z', href: 'https://sonarr/series/1', posterUrl: null },
            { title: 'Show A S01E01', when: '2026-03-24T20:00:00Z', href: 'https://sonarr/series/1', posterUrl: null },
          ],
          itemCount: 2,
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    const root = fixtureHost(fixture);
    const details = root.querySelector('details.show-card');
    expect(details).toBeTruthy();
    const detailsEl = details as HTMLDetailsElement;
    detailsEl.open = true;
    fixture.detectChanges();

    const eps = detailsEl.querySelectorAll('.show-card__eps a.ep');
    expect(eps).toHaveLength(2);
    expect(eps[0].textContent).toContain('Episode 1');
    expect(eps[1].textContent).toContain('Episode 1');
  });

  it('renders two separate cards for identical items from different Sonarr problems', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'degraded', detail: '2 missing · 1 shows · 0 queued', latencyMs: 20 },
      ],
      problems: [
        {
          id: 'same-id',
          summary: 'Missing episode batch 1',
          serviceId: 'sonarr',
          severity: 'warning',
          items: [
            { title: 'Show A S01E01', when: '2026-03-24T20:00:00Z', href: 'https://sonarr/series/1', posterUrl: null },
          ],
          itemCount: 1,
        },
        {
          id: 'same-id',
          summary: 'Missing episode batch 2',
          serviceId: 'sonarr',
          severity: 'warning',
          items: [
            { title: 'Show A S01E01', when: '2026-03-24T20:00:00Z', href: 'https://sonarr/series/1', posterUrl: null },
          ],
          itemCount: 1,
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    const root = fixtureHost(fixture);
    const cards = root.querySelectorAll('.show-card');
    expect(cards).toHaveLength(2);
    // Ensure same-problem grouping still works (one problem, two items → one details card)
    expect(root.querySelectorAll('details.show-card')).toHaveLength(0);
  });

  it('treats Radarr items with SxxExx pattern title as individual movies, not grouped episodes', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'radarr', name: 'Radarr', status: 'degraded', detail: '2 missing · 2 movies · 0 queued', latencyMs: 20 },
      ],
      problems: [
        {
          id: 'radarr-missing',
          summary: '2 movies missing',
          serviceId: 'radarr',
          severity: 'warning',
          items: [
            { title: 'Movie S01E01', when: '2026-06-01T20:00:00Z', href: 'https://radarr/movie/1', posterUrl: null },
            { title: 'Movie S01E01', when: '2026-06-02T20:00:00Z', href: 'https://radarr/movie/2', posterUrl: null },
          ],
          itemCount: 2,
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    const root = fixtureHost(fixture);
    const anchors = root.querySelectorAll('a.show-card');
    expect(anchors).toHaveLength(2);
    expect(root.querySelector('details.show-card')).toBeNull();
    expect(anchors[0].textContent).toContain('Movie S01E01');
    expect(anchors[1].textContent).toContain('Movie S01E01');
  });

  describe('contract: ARR_DETAIL_RE detail format', () => {
    it('pins sonarr canonical: "N missing · N shows · N queued"', () => {
      health.status.set('ready');
      health.summary.set({
        generatedAt: '',
        services: [
          { id: 'sonarr', name: 'Sonarr', status: 'degraded', detail: '34 missing · 17 shows · 1 queued', latencyMs: 20 },
        ],
        problems: [],
        preview: [],
        availability: { services: 'present', preview: 'empty', problems: 'present' },
      });
      seedStorage();
      fixture.detectChanges();

      fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
      const root = fixtureHost(fixture);
      const stats = root.querySelectorAll('.stat');
      expect(stats).toHaveLength(3);
      expect(stats[0].textContent).toContain('34');
      expect(stats[0].textContent).toContain('Missing');
      expect(stats[1].textContent).toContain('17');
      expect(stats[1].textContent).toContain('Shows');
      expect(stats[2].textContent).toContain('1');
      expect(stats[2].textContent).toContain('Queued');
    });

    it('pins radarr canonical: "N missing · N movies · N queued"', () => {
      health.status.set('ready');
      health.summary.set({
        generatedAt: '',
        services: [
          { id: 'radarr', name: 'Radarr', status: 'degraded', detail: '5 missing · 3 movies · 0 queued', latencyMs: 20 },
        ],
        problems: [],
        preview: [],
        availability: { services: 'present', preview: 'empty', problems: 'present' },
      });
      seedStorage();
      fixture.detectChanges();

      fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
      const root = fixtureHost(fixture);
      const stats = root.querySelectorAll('.stat');
      expect(stats).toHaveLength(3);
      expect(stats[0].textContent).toContain('5');
      expect(stats[0].textContent).toContain('Missing');
      expect(stats[1].textContent).toContain('3');
      expect(stats[1].textContent).toContain('Movies');
      expect(stats[2].textContent).toContain('0');
      expect(stats[2].textContent).toContain('Queued');
    });

    it('yields null for non-matching detail format so backend changes fail loud', () => {
      health.status.set('ready');
      health.summary.set({
        generatedAt: '',
        services: [
          { id: 'sonarr', name: 'Sonarr', status: 'degraded', detail: '34 missing : 17 shows : 1 queued', latencyMs: 20 },
        ],
        problems: [],
        preview: [],
        availability: { services: 'present', preview: 'empty', problems: 'present' },
      });
      seedStorage();
      fixture.detectChanges();

      fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
      const root = fixtureHost(fixture);
      expect(root.querySelectorAll('.stat')).toHaveLength(0);
    });
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

  it.each([
    { id: 'sonarr', name: 'Sonarr', detail: '1 missing · 1 shows · 0 queued', summary: 'Sonarr cannot reach indexer' },
    { id: 'radarr', name: 'Radarr', detail: '1 missing · 1 movies · 0 queued', summary: 'Radarr cannot connect to indexer' },
  ])('shows $name problem summary when problem has no items (D1)', ({ id, name, detail, summary }) => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id, name, status: 'degraded' as const, detail, latencyMs: 20 },
      ],
      problems: [
        {
          id: `${id}-missing`,
          summary,
          serviceId: id,
          severity: 'actionable',
          items: [],
          itemCount: 0,
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    fixture.detectChanges();
    const dialog = fixtureHost(fixture).querySelector('dialog');
    expect(dialog?.textContent).toContain(summary);
  });

  it('shows service status and detail in generic non-Arr dialog (D4)', () => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'prowlarr', name: 'Prowlarr', status: 'degraded', detail: 'Indexer lag', latencyMs: 40 },
      ],
      problems: [
        {
          id: 'problem-1',
          summary: 'Prowlarr indexer response slow',
          serviceId: 'prowlarr',
          severity: 'warning',
        },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    fixtureHost(fixture).querySelector<HTMLButtonElement>('.svc__trigger')?.click();
    fixture.detectChanges();
    const dialog = fixtureHost(fixture).querySelector('dialog');
    expect(dialog?.textContent).toContain('Degraded');
    expect(dialog?.textContent).toContain('Indexer lag');
  });

  it.each([
    { status: 'healthy' as const, expectedClass: 'svc__status--ok' },
    { status: 'degraded' as const, expectedClass: 'svc__status--degraded' },
    { status: 'down' as const, expectedClass: 'svc__status--down' },
  ])('wraps $status dot inside $expectedClass', ({ status, expectedClass }) => {
    health.status.set('ready');
    health.summary.set({
      generatedAt: '',
      services: [
        { id: 'prowlarr', name: 'Prowlarr', status, detail: 'Status detail', latencyMs: 40 },
      ],
      problems: [
        { id: 'p-1', summary: 'Problem', serviceId: 'prowlarr', severity: 'actionable' },
      ],
      preview: [],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    });
    seedStorage();
    fixture.detectChanges();

    const service = health.services()[0];
    fixture.componentInstance.openService(service);
    fixture.detectChanges();
    const dialog = fixtureHost(fixture).querySelector('dialog');
    const wrapper = dialog?.querySelector(`.${expectedClass}`);
    expect(wrapper).toBeTruthy();
    expect(wrapper?.querySelector('.dot')).toBeTruthy();
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

