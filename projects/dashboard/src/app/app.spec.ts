import { Location } from '@angular/common';
import { provideLocationMocks, SpyLocation } from '@angular/common/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { App } from './app';
import { routes } from './app.routes';
import { ServiceHealthFacade } from './automation/service-health.facade';
import { MEDIA_STACK_API } from './media-stack/media-stack-api';
import { provideOperationalLinkBases } from './media-stack/media-stack-api.providers';
import { MockMediaStackApi } from './media-stack/mock-media-stack-api';

describe('App shell', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter(routes),
        provideLocationMocks(),
        { provide: MEDIA_STACK_API, useClass: MockMediaStackApi },
        ...provideOperationalLinkBases(),
      ],
    });
  });

  it('renders the shell and its primary navigation', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.brand')?.textContent).toContain('Media Manager');
    expect(fixture.nativeElement.querySelector('.demo-badge')?.textContent).toContain('Demo');
    expect(fixture.nativeElement.querySelectorAll('.sidebar__nav a')).toHaveLength(3);
    expect(fixture.nativeElement.querySelectorAll('.service-link')).toHaveLength(7);
    expect(fixture.nativeElement.querySelector('router-outlet')).toBeTruthy();
  });

  it('wires SERVICE_LINK_BASES into sidebar anchors and keeps SABnzbd inert', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    const byName = new Map(fixture.componentInstance.services().map((service) => [service.name, service]));
    expect(byName.get('Jellyfin')?.href).toBe('http://localhost:8096/');
    expect(byName.get('Sonarr')?.href).toBe('http://localhost:8989/');
    expect(byName.get('SABnzbd')?.href).toBeNull();

    const jellyfin = [...fixture.nativeElement.querySelectorAll('.service-link')].find((el: Element) =>
      el.textContent.includes('Jellyfin'),
    ) as HTMLAnchorElement | undefined;
    expect(jellyfin?.tagName).toBe('A');
    expect(jellyfin?.getAttribute('href')).toBe('http://localhost:8096/');

    const sabnzbd = [...fixture.nativeElement.querySelectorAll('.service-link')].find((el: Element) =>
      el.textContent.includes('SABnzbd'),
    ) as HTMLElement | undefined;
    expect(sabnzbd?.tagName).toBe('SPAN');
    expect(sabnzbd?.classList.contains('service-link--inert')).toBe(true);
  });

  it('overlays sidebar service status from live health and leaves untracked services unknown', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(fixture.componentInstance.services().every((service) => service.status === 'unknown')).toBe(true);
    expect(fixture.nativeElement.querySelector('.service-dot--unknown')).toBeTruthy();

    const health = TestBed.inject(ServiceHealthFacade);
    await health.refresh({ initial: true });
    fixture.detectChanges();

    const byName = new Map(fixture.componentInstance.services().map((service) => [service.name, service]));
    expect(byName.get('Sonarr')?.status).toBe('healthy');
    expect(byName.get('Prowlarr')?.status).toBe('degraded');
    expect(byName.get('SABnzbd')?.status).toBe('offline');
    expect(byName.get('Jellyfin')?.status).toBe('healthy');
    expect(byName.get('qBittorrent')?.status).toBe('healthy');
  });

  it('conditionally includes SABnzbd based on environment.useLiveApi', () => {
    const fixture = TestBed.createComponent(App);
    // SABnzbd is catalogued as demoOnly and filtered when useLiveApi is true.
    const names = fixture.componentInstance.services().map((s) => s.name);
    expect(names).toContain('SABnzbd');
  });

  it.each([
    ['/', 'Dashboard', null],
    ['/dashboard', 'Dashboard', null],
    ['/reports', 'Reports', 'Failed and actionable automation runs first'],
    ['/discover', 'Discover', 'Browse Hermes, Jellyseerr, and Trakt recommendations'],
  ])('recognizes %s as %s and renders its destination', async (url, heading, lede) => {
    const harness = await RouterTestingHarness.create();
    const router = TestBed.inject(Router);
    await harness.navigateByUrl(url);
    expect(router.url).toBe(url === '/dashboard' ? '/' : url);
    expect(router.routerState.snapshot.root.firstChild?.routeConfig?.path).toBe(url === '/' || url === '/dashboard' ? '' : url.slice(1));
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
