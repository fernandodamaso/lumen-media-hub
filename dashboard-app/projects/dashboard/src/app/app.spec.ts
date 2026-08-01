import { Location } from '@angular/common';
import { provideLocationMocks, SpyLocation } from '@angular/common/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { vi } from 'vitest';
import { fixtureHost } from '../testing/fixture-host';
import { App } from './app';
import { routes } from './app.routes';
import { provideHttpClient } from '@angular/common/http';
import { ActivityFacade } from './right-rail/activity.facade';
import { AutomationFacade } from './automation/automation.facade';
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
    ActivityFacade,
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
    expect(root.querySelector('.demo-badge')).toBeNull();
    expect(root.querySelectorAll('.sidebar__nav a')).toHaveLength(4);
    expect(root.querySelector('[data-testid="search-trigger"]')).toBeNull();
    expect(root.querySelector('[data-testid="topbar-search"]')).toBeTruthy();
    expect(root.querySelector('mm-right-rail')).toBeTruthy();
    expect(root.querySelectorAll('.service-link')).toHaveLength(0);
    expect(root.querySelector('router-outlet')).toBeTruthy();
  });

  it('does not render the retired status pill or manage-storage link', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    const health = TestBed.inject(ServiceHealthFacade);
    await health.refresh({ initial: true });
    const storage = TestBed.inject(StorageFacade);
    await storage.refresh({ initial: true });
    fixture.detectChanges();

    expect(fixtureHost(fixture).querySelector('[data-testid="status-pill"]')).toBeNull();
    expect(fixtureHost(fixture).querySelector('.mini-card__manage')).toBeNull();
  });

  it('opens the command palette signal from the topbar search pill', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(fixture.componentInstance.commandPaletteOpen()).toBe(false);

    const trigger = fixtureHost(fixture).querySelector('[data-testid="topbar-search"]') as HTMLButtonElement;
    trigger.click();
    await Promise.resolve();
    fixture.detectChanges();
    expect(fixture.componentInstance.commandPaletteOpen()).toBe(true);
  });

  it('shows the storage mini-card once a library volume is loaded', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('[data-testid="storage-mini-card"]')).toBeNull();

    const storage = TestBed.inject(StorageFacade);
    await storage.refresh({ initial: true });
    fixture.detectChanges();

    const card = fixtureHost(fixture).querySelector('[data-testid="storage-mini-card"]');
    expect(card).toBeTruthy();
    expect(card?.textContent).toContain('Storage');
    expect(card?.textContent).not.toContain('Manage storage');
  });

  it('keeps shell-owned polling armed across Dashboard → Library → Dashboard navigation', async () => {
    const calendar = TestBed.inject(CalendarFacade);
    const automation = TestBed.inject(AutomationFacade);
    const storage = TestBed.inject(StorageFacade);
    const activity = TestBed.inject(ActivityFacade);
    const downloads = TestBed.inject(DownloadsFacade);
    const calendarStart = vi.spyOn(calendar, 'startPolling');
    const calendarStop = vi.spyOn(calendar, 'stopPolling');
    const automationStop = vi.spyOn(automation, 'stopPolling');
    const storageStop = vi.spyOn(storage, 'stopPolling');
    const activityStop = vi.spyOn(activity, 'stopPolling');
    const downloadsStart = vi.spyOn(downloads, 'startPolling');
    const downloadsStop = vi.spyOn(downloads, 'stopPolling');

    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(calendarStart).toHaveBeenCalledTimes(1);

    const router = TestBed.inject(Router);
    await router.navigateByUrl('/');
    fixture.detectChanges();
    expect(downloadsStart).toHaveBeenCalledTimes(1);

    await calendar.refresh({ initial: true });
    const statusOnDashboard = calendar.status();
    expect(statusOnDashboard === 'ready' || statusOnDashboard === 'empty').toBe(true);

    await router.navigateByUrl('/library');
    fixture.detectChanges();
    expect(downloadsStop).toHaveBeenCalledTimes(1);
    expect(calendarStop).not.toHaveBeenCalled();
    expect(automationStop).not.toHaveBeenCalled();
    expect(storageStop).not.toHaveBeenCalled();
    expect(activityStop).not.toHaveBeenCalled();

    await router.navigateByUrl('/');
    fixture.detectChanges();
    expect(downloadsStart).toHaveBeenCalledTimes(2);
    expect(calendarStart).toHaveBeenCalledTimes(1);
    expect(calendar.status()).toBe(statusOnDashboard);
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
