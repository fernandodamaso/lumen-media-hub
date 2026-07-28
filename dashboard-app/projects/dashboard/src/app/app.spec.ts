import { Location } from '@angular/common';
import { provideLocationMocks, SpyLocation } from '@angular/common/testing';
import { computed, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { vi } from 'vitest';
import { fixtureHost } from '../testing/fixture-host';
import { App } from './app';
import { routes } from './app.routes';
import { provideHttpClient } from '@angular/common/http';
import { AutomationFacade } from './automation/automation.facade';
import { summarizeAutomationHealth } from './automation/automation.models';
import { ServiceHealthFacade } from './automation/service-health.facade';
import { CalendarFacade } from './calendar/calendar.facade';
import { DownloadsFacade } from './downloads/downloads.facade';
import { LibraryStatsFacade } from './library/library-stats.facade';
import { MEDIA_STACK_API } from './media-stack/media-stack-api';
import { provideOperationalLinkBases } from './media-stack/media-stack-api.providers';
import { MockMediaStackApi } from './media-stack/mock-media-stack-api';
import { StorageFacade } from './storage/storage.facade';

function provideCommandPaletteFacadeMocks() {
  return [
    provideHttpClient(),
    CalendarFacade,
    DownloadsFacade,
    LibraryStatsFacade,
    StorageFacade,
    AutomationFacade,
  ];
}

describe('App shell', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter(routes),
        provideLocationMocks(),
        {
          provide: MEDIA_STACK_API,
          useFactory: () => {
            const api = new MockMediaStackApi();
            api.latencyMs = 0;
            return api;
          },
        },
        ...provideOperationalLinkBases(),
        ...provideCommandPaletteFacadeMocks(),
      ],
    });
  });

  it('renders the shell and its primary navigation', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const root = fixtureHost(fixture);

    expect(root.querySelector('.brand')?.textContent).toContain('Media Manager');
    expect(root.querySelector('.demo-badge')?.textContent).toContain('Demo');
    expect(root.querySelectorAll('.sidebar__nav a')).toHaveLength(4);
    expect(root.querySelector('[data-testid="search-trigger"]')).toBeTruthy();
    expect(root.querySelectorAll('.service-link')).toHaveLength(0);
    expect(root.querySelector('router-outlet')).toBeTruthy();
  });

  it('shows a status pill when services need attention', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('[data-testid="status-pill"]')).toBeNull();

    const health = TestBed.inject(ServiceHealthFacade);
    await health.refresh({ initial: true });
    fixture.detectChanges();

    const pill = fixtureHost(fixture).querySelector('[data-testid="status-pill"]');
    expect(pill).toBeTruthy();
    expect(pill?.getAttribute('href') ?? pill?.getAttribute('ng-reflect-router-link')).toBeTruthy();
    expect(pill?.textContent).toMatch(/need attention/);
  });

  it('opens the command palette signal from the search trigger', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(fixture.componentInstance.commandPaletteOpen()).toBe(false);

    const trigger = fixtureHost(fixture).querySelector('[data-testid="search-trigger"]') as HTMLButtonElement;
    trigger.click();
    await Promise.resolve();
    fixture.detectChanges();
    expect(fixture.componentInstance.commandPaletteOpen()).toBe(true);
  });

  it('labels the status pill from problem count when services are otherwise healthy', () => {
    TestBed.resetTestingModule();
    const summary = signal({
      generatedAt: '',
      services: [{ id: 'jellyfin', name: 'Jellyfin', status: 'healthy' as const, detail: '', latencyMs: 10 }],
      problems: [
        { id: 'p1', summary: 'Indexer cooldown', serviceId: 'prowlarr', severity: 'info' as const },
      ],
      preview: [],
      availability: {
        services: 'present' as const,
        preview: 'empty' as const,
        problems: 'present' as const,
      },
    });
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter(routes),
        provideLocationMocks(),
        {
          provide: MEDIA_STACK_API,
          useFactory: () => {
            const api = new MockMediaStackApi();
            api.latencyMs = 0;
            return api;
          },
        },
        ...provideOperationalLinkBases(),
        {
          provide: ServiceHealthFacade,
          useValue: {
            status: signal('ready'),
            summary,
            services: computed(() => summary().services),
            problems: computed(() => summary().problems),
            health: computed(() => summarizeAutomationHealth(summary())),
            error: signal(''),
            startPolling: vi.fn(),
            refresh: vi.fn(),
          },
        },
        ...provideCommandPaletteFacadeMocks(),
      ],
    });

    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const pill = fixtureHost(fixture).querySelector('[data-testid="status-pill"]');
    expect(pill?.textContent).toMatch(/1 service need attention/);
    expect(pill?.textContent).not.toContain('0 services');
  });

  it('counts unique services in the attention pill, not problem rows', () => {
    TestBed.resetTestingModule();
    const summary = signal({
      generatedAt: '',
      services: [
        { id: 'sonarr', name: 'Sonarr', status: 'degraded' as const, detail: 'Missing episodes', latencyMs: 10 },
        { id: 'radarr', name: 'Radarr', status: 'healthy' as const, detail: '', latencyMs: 10 },
      ],
      problems: [
        { id: 'p1', summary: 'Missing ep 1', serviceId: 'sonarr', severity: 'actionable' as const },
        { id: 'p2', summary: 'Missing ep 2', serviceId: 'sonarr', severity: 'actionable' as const },
        { id: 'p3', summary: 'Missing ep 3', serviceId: 'sonarr', severity: 'actionable' as const },
        { id: 'p4', summary: 'Missing ep 4', serviceId: 'sonarr', severity: 'actionable' as const },
        { id: 'p5', summary: 'Missing ep 5', serviceId: 'sonarr', severity: 'actionable' as const },
      ],
      preview: [],
      availability: {
        services: 'present' as const,
        preview: 'empty' as const,
        problems: 'present' as const,
      },
    });
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter(routes),
        provideLocationMocks(),
        {
          provide: MEDIA_STACK_API,
          useFactory: () => {
            const api = new MockMediaStackApi();
            api.latencyMs = 0;
            return api;
          },
        },
        ...provideOperationalLinkBases(),
        {
          provide: ServiceHealthFacade,
          useValue: {
            status: signal('ready'),
            summary,
            services: computed(() => summary().services),
            problems: computed(() => summary().problems),
            health: computed(() => summarizeAutomationHealth(summary())),
            error: signal(''),
            startPolling: vi.fn(),
            refresh: vi.fn(),
          },
        },
        ...provideCommandPaletteFacadeMocks(),
      ],
    });

    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const pill = fixtureHost(fixture).querySelector('[data-testid="status-pill"]');
    expect(pill?.textContent).toMatch(/1 service need attention/);
    expect(pill?.textContent).not.toContain('5 services');
  });

  it.each([
    ['/', 'Dashboard', null],
    ['/dashboard', 'Dashboard', null],
    ['/library', 'Library', null],
    ['/reports', 'Reports', 'Failed and actionable automation runs first'],
    ['/discover', 'Discover', 'Browse Hermes, Jellyseerr, and Trakt recommendations'],
  ])('recognizes %s as %s and renders its destination', async (url, heading, lede) => {
    const harness = await RouterTestingHarness.create();
    const router = TestBed.inject(Router);
    await harness.navigateByUrl(url);
    expect(router.url).toBe(url === '/dashboard' ? '/' : url);
    expect(router.routerState.snapshot.root.firstChild?.routeConfig?.path).toBe(
      url === '/' || url === '/dashboard' ? '' : url.slice(1),
    );
    expect(harness.routeNativeElement?.textContent).toContain(heading);
    if (lede) {
      expect(harness.routeNativeElement?.textContent).toContain(lede);
    }
  });

  it('navigates between destinations and restores browser history', async () => {
    const harness = await RouterTestingHarness.create();
    const location = TestBed.inject(Location) as SpyLocation;
    const router = TestBed.inject(Router);

    router.setUpLocationChangeListener();
    await harness.navigateByUrl('/reports');
    expect(router.url).toBe('/reports');

    await harness.navigateByUrl('/discover');
    expect(router.url).toBe('/discover');

    location.back();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(router.url).toBe('/reports');
  });
});
