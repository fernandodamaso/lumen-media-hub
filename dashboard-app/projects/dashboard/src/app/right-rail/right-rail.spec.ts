import { computed, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { AutomationSummary, summarizeAutomationHealth } from '../automation/automation.models';
import { CalendarFacade, CalendarRailEvent, CalendarStatus } from '../calendar/calendar.facade';
import { ActivityItem, ActivityFeed } from '../activity/activity.models';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { fixtureHost } from '../../testing/fixture-host';
import { ActivityFacade, ActivityStatus } from './activity.facade';
import { RightRail } from './right-rail';

const upcomingEvent: CalendarRailEvent = {
  id: 'ep-1',
  title: 'Duel of Suns',
  subtitle: 'S1E6 · Episode 6',
  time: '21:00',
  kind: 'episode',
  status: 'pending',
  airDate: '2026-08-01T21:00:00Z',
  href: 'http://sonarr.local/series/duel-of-suns',
};

const activityItem: ActivityItem = {
  id: 'sonarr:48211',
  source: 'sonarr',
  kind: 'imported',
  title: 'The Shōgun Court',
  subtitle: 'S01E07 · 1080p WEB-DL',
  timestamp: '2026-07-30T00:18:41Z',
  href: 'http://sonarr.local/series/shogun-court',
};

function summaryWith(statuses: ('healthy' | 'degraded' | 'down' | 'unknown')[]): AutomationSummary {
  return {
    generatedAt: new Date().toISOString(),
    services: statuses.map((status, index) => ({
      id: `svc-${index}`,
      name: `Service ${index}`,
      status,
      detail: '',
      latencyMs: 10,
    })),
    problems: [],
    preview: [],
    availability: { services: 'present', preview: 'empty', problems: 'empty' },
  };
}

describe('RightRail', () => {
  const calendarEvents = signal<CalendarRailEvent[]>([]);
  const calendarStatus = signal<CalendarStatus>('loading');
  const calendarDegradedSources = signal<string[]>([]);
  const activityFeed = signal<ActivityFeed | null>(null);
  const activityStatus = signal<ActivityStatus>('loading');
  const automationSummary = signal<AutomationSummary | null>(null);
  const healthError = signal('');

  beforeEach(() => {
    calendarEvents.set([]);
    calendarStatus.set('loading');
    calendarDegradedSources.set([]);
    activityFeed.set(null);
    activityStatus.set('loading');
    automationSummary.set(null);
    healthError.set('');

    TestBed.configureTestingModule({
      imports: [RightRail],
      providers: [
        provideRouter([{ path: 'reports', children: [] }]),
        {
          provide: SERVICE_LINK_BASES,
          useValue: { sonarr: 'http://sonarr.local', jellyfin: 'http://jellyfin.local' },
        },
        {
          provide: CalendarFacade,
          useValue: {
            status: calendarStatus,
            events: calendarEvents,
            degradedSources: calendarDegradedSources,
            error: signal(''),
            refresh: vi.fn(),
          },
        },
        {
          provide: ActivityFacade,
          useValue: {
            status: activityStatus,
            items: computed(() => activityFeed()?.items ?? []),
            sources: computed(
              () => activityFeed()?.sources ?? { sonarr: 'unconfigured', radarr: 'unconfigured' },
            ),
            degradedSources: computed(() =>
              (Object.entries(
                activityFeed()?.sources ?? { sonarr: 'unconfigured', radarr: 'unconfigured' },
              ))
                .filter(([, state]) => state === 'error')
                .map(([name]) => name),
            ),
            error: signal(''),
            refresh: vi.fn(),
          },
        },
        {
          provide: ServiceHealthFacade,
          useValue: {
            status: signal('ready'),
            services: computed(() => automationSummary()?.services ?? []),
            health: computed(() => {
              const summary = automationSummary();
              return summary
                ? summarizeAutomationHealth(summary)
                : { overall: 'unknown' as const, actionableCount: 0 };
            }),
            error: healthError,
            refresh: vi.fn(),
          },
        },
      ],
    });
  });

  it('renders upcoming releases with a Ready chip for available events', () => {
    calendarStatus.set('ready');
    calendarEvents.set([{ ...upcomingEvent, status: 'available' }, { ...upcomingEvent, id: 'ep-2' }]);
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const rows = root.querySelectorAll('[data-testid="rr-upcoming"] mm-upcoming-item');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('Ready');
    expect(root.querySelector('[data-testid="rr-upcoming"] h3 a')?.getAttribute('href')).toBe(
      'http://sonarr.local/calendar',
    );
  });

  it('warns when a calendar source fails but the calendar still loaded', () => {
    calendarStatus.set('ready');
    calendarDegradedSources.set(['sonarr']);
    calendarEvents.set([upcomingEvent]);
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();

    const section = fixtureHost(fixture).querySelector('[data-testid="rr-upcoming"]');
    expect(section?.querySelector('.rail-note--warning')?.textContent).toContain('sonarr');
    expect(section?.querySelectorAll('mm-upcoming-item')).toHaveLength(1);
  });

  it('does not show a partial-calendar warning when the calendar load failed completely', () => {
    calendarStatus.set('error');
    calendarDegradedSources.set(['sonarr', 'radarr']);
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();

    const section = fixtureHost(fixture).querySelector('[data-testid="rr-upcoming"]');
    expect(section?.querySelector('.rail-note--warning')).toBeNull();
    expect(section?.querySelector('.rail-note--danger')?.textContent).toContain('Calendar is unavailable');
  });

  it('renders activity rows with relative time and external links', () => {
    activityStatus.set('ready');
    activityFeed.set({
      ok: true,
      generatedAt: '',
      sources: { sonarr: 'ok', radarr: 'ok' },
      items: [activityItem],
    });
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();

    const row = fixtureHost(fixture).querySelector('[data-testid="rr-activity"] .act-row');
    expect(row?.textContent).toContain('The Shōgun Court');
    expect(row?.textContent).toContain('S01E07 · 1080p WEB-DL');
    expect(row?.querySelector('a.act-txt')?.getAttribute('href')).toBe(
      'http://sonarr.local/series/shogun-court',
    );
    const time = row?.querySelector('.act-time')?.textContent ?? '';
    expect(time.trim()).not.toBe('');
  });

  it('warns when an activity source is degraded but keeps rows visible', () => {
    activityStatus.set('ready');
    activityFeed.set({
      ok: true,
      generatedAt: '',
      sources: { sonarr: 'error', radarr: 'ok' },
      items: [activityItem],
    });
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();

    const section = fixtureHost(fixture).querySelector('[data-testid="rr-activity"]');
    expect(section?.querySelector('.rail-note--warning')?.textContent).toContain('sonarr');
    expect(section?.querySelectorAll('.act-row')).toHaveLength(1);
  });

  it('shows the all-good banner only when every service is healthy', () => {
    automationSummary.set(summaryWith(['healthy', 'healthy']));
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('[data-testid="rr-all-good"]')).toBeTruthy();
    expect(fixtureHost(fixture).querySelectorAll('[data-testid="rr-health"] mm-service-row')).toHaveLength(2);

    automationSummary.set(summaryWith(['healthy', 'degraded']));
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('[data-testid="rr-all-good"]')).toBeNull();
  });

  it('renders a brand icon for known services', () => {
    automationSummary.set({
      ...summaryWith(['healthy']),
      services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: '', latencyMs: 10 }],
    });
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();

    expect(
      fixtureHost(fixture).querySelector('[data-testid="rr-health"] img.svc-ico-img')?.getAttribute('src'),
    ).toBe('icons/services/sonarr.svg');
  });

  it('shows a health warning while retaining the healthy snapshot rows', () => {
    automationSummary.set(summaryWith(['healthy', 'healthy']));
    healthError.set('Could not refresh service health. Showing last loaded status.');
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();

    const section = fixtureHost(fixture).querySelector('[data-testid="rr-health"]');
    expect(section?.querySelector('.rail-note--warning')?.textContent).toContain('Could not refresh');
    expect(section?.querySelectorAll('mm-service-row')).toHaveLength(2);
    expect(section?.querySelector('[data-testid="rr-all-good"]')).toBeNull();
  });

  it('renders skeletons while sections load', () => {
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();
    expect(
      fixtureHost(fixture).querySelectorAll('[data-testid="rr-upcoming"] mm-skeleton').length,
    ).toBeGreaterThan(0);
  });

  it('links configured service names externally and degraded statuses to Reports', () => {
    automationSummary.set({
      ...summaryWith(['degraded']),
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'degraded', detail: 'Indexers slow', latencyMs: 350 },
      ],
    });
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();

    const section = fixtureHost(fixture).querySelector('[data-testid="rr-health"]');
    const nameLink = section?.querySelector('.svc-name--link');
    const statusLink = section?.querySelector('.svc-status--link');
    expect(nameLink?.getAttribute('href')).toBe('http://sonarr.local/');
    expect(nameLink?.getAttribute('target')).toBe('_blank');
    expect(statusLink?.getAttribute('href')).toBe('/reports?service=sonarr#service-health');
  });

  it('links healthy service names but keeps healthy statuses plain text', () => {
    automationSummary.set({
      ...summaryWith(['healthy']),
      services: [{ id: 'jellyfin', name: 'Jellyfin', status: 'healthy', detail: 'Streaming ready', latencyMs: 18 }],
    });
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();

    const section = fixtureHost(fixture).querySelector('[data-testid="rr-health"]');
    expect(section?.querySelector('.svc-name--link')?.getAttribute('href')).toBe('http://jellyfin.local/');
    expect(section?.querySelector('.svc-status--link')).toBeNull();
    expect(section?.querySelector('.svc-status')?.textContent).toContain('Healthy');
  });

  it('routes down services to Reports even when the external name link is unavailable', () => {
    automationSummary.set({
      ...summaryWith(['down']),
      services: [{ id: 'sabnzbd', name: 'SABnzbd', status: 'down', detail: 'Last seen 18m ago' }],
    });
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();

    const section = fixtureHost(fixture).querySelector('[data-testid="rr-health"]');
    expect(section?.querySelector('.svc-name--link')).toBeNull();
    expect(section?.querySelector('.svc-status--link')?.getAttribute('href')).toBe(
      '/reports?service=sabnzbd#service-health',
    );
  });

  it('keeps unknown statuses as plain text', () => {
    automationSummary.set({
      ...summaryWith(['unknown']),
      services: [{ id: 'unpackerr', name: 'Unpackerr', status: 'unknown', detail: 'No data', latencyMs: null }],
    });
    const fixture = TestBed.createComponent(RightRail);
    fixture.detectChanges();

    const section = fixtureHost(fixture).querySelector('[data-testid="rr-health"]');
    expect(section?.querySelector('.svc-status--link')).toBeNull();
    expect(section?.querySelector('.svc-status')?.textContent).toContain('Unknown');
  });
});