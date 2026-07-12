import { Location } from '@angular/common';
import { provideLocationMocks, SpyLocation } from '@angular/common/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { App } from './app';
import { routes } from './app.routes';
import { MEDIA_STACK_API, MEDIA_STACK_API_MODE } from './downloads/media-stack-api';
import { MockMediaStackApi } from './downloads/mock-media-stack-api';

describe('App shell', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter(routes), provideLocationMocks(), { provide: MEDIA_STACK_API_MODE, useValue: 'mock' }, { provide: MEDIA_STACK_API, useClass: MockMediaStackApi }],
    });
  });

  it('renders the shell and its primary navigation', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.brand')?.textContent).toContain('Media Manager');
    expect(fixture.nativeElement.querySelector('.demo-badge')?.textContent).toContain('Demo');
    expect(fixture.nativeElement.querySelectorAll('nav a')).toHaveLength(4);
    expect(fixture.nativeElement.querySelector('router-outlet')).toBeTruthy();
  });

  it.each([
    ['/', 'Dashboard', 'Your media workspace is ready for the next slice.'],
    ['/dashboard', 'Dashboard', 'Your media workspace is ready for the next slice.'],
    ['/reports', 'Reports', 'Reporting tools will live here.'],
    ['/discover', 'Discover', 'Browse and collect new media from this space.'],
    ['/ui', 'UI catalog', 'Explore the shared primitives that power the dashboard shell.'],
  ])('recognizes %s as %s and renders its destination', async (url, heading, lede) => {
    const harness = await RouterTestingHarness.create();
    const router = TestBed.inject(Router);
    await harness.navigateByUrl(url);
    expect(router.url).toBe(url === '/dashboard' ? '/' : url);
    expect(router.routerState.snapshot.root.firstChild?.routeConfig?.path).toBe(url === '/' || url === '/dashboard' ? '' : url.slice(1));
    expect(harness.routeNativeElement?.querySelector('h1')?.textContent).toContain(heading);
    expect(harness.routeNativeElement?.textContent).toContain(lede);
  });

  it('navigates between destinations and restores browser history', async () => {
    const harness = await RouterTestingHarness.create();
    const location = TestBed.inject(Location) as SpyLocation;
    const router = TestBed.inject(Router);

    router.setUpLocationChangeListener();
    await harness.navigateByUrl('/reports');
    await harness.navigateByUrl('/discover');
    expect(location.path()).toBe('/discover');

    location.back();
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    expect(location.path()).toBe('/reports');
    expect(router.url).toBe('/reports');
    expect(harness.routeNativeElement?.querySelector('h1')?.textContent).toContain('Reports');
  });
});
