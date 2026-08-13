import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { fixtureHost } from '../../testing/fixture-host';
import { MmServiceRow } from './service-row';

describe('MmServiceRow', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [MmServiceRow],
      providers: [provideRouter([{ path: 'reports', children: [] }])],
    });
  });

  it('renders configured service names as external links', () => {
    const fixture = TestBed.createComponent(MmServiceRow);
    fixture.componentRef.setInput('name', 'Sonarr');
    fixture.componentRef.setInput('nameHref', 'http://sonarr.local/');
    fixture.detectChanges();

    const link = fixtureHost(fixture).querySelector('.svc-name--link');
    expect(link?.getAttribute('href')).toBe('http://sonarr.local/');
    expect(link?.getAttribute('target')).toBe('_blank');
    expect(link?.getAttribute('rel')).toBe('noreferrer');
    expect(link?.getAttribute('aria-label')).toBe('Open Sonarr');
  });

  it('keeps service names as plain text when no href is configured', () => {
    const fixture = TestBed.createComponent(MmServiceRow);
    fixture.componentRef.setInput('name', 'Unpackerr');
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.svc-name--link')).toBeNull();
    expect(root.querySelector('.svc-name')?.textContent).toBe('Unpackerr');
  });

  it('renders problem statuses as router links with accessible labels', () => {
    const router = TestBed.inject(Router);
    const statusLink = router.createUrlTree(['/reports'], {
      queryParams: { service: 'sonarr' },
      fragment: 'service-health',
    });
    const fixture = TestBed.createComponent(MmServiceRow);
    fixture.componentRef.setInput('name', 'Sonarr');
    fixture.componentRef.setInput('status', 'degraded');
    fixture.componentRef.setInput('statusLabel', 'Degraded');
    fixture.componentRef.setInput('statusLink', statusLink);
    fixture.detectChanges();

    const link = fixtureHost(fixture).querySelector('.svc-status--link');
    expect(link?.getAttribute('href')).toBe('/reports?service=sonarr#service-health');
    expect(link?.getAttribute('aria-label')).toBe('View Sonarr live health report');
    expect(link?.textContent).toContain('Degraded');
  });

  it('keeps healthy and unknown statuses as plain text', () => {
    const fixture = TestBed.createComponent(MmServiceRow);
    fixture.componentRef.setInput('name', 'Jellyfin');
    fixture.componentRef.setInput('status', 'healthy');
    fixture.componentRef.setInput('statusLabel', 'Healthy');
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.svc-status--link')).toBeNull();
    expect(root.querySelector('.svc-status')?.textContent).toContain('Healthy');
  });
});
