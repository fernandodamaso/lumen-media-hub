import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { AutomationService } from '../automation/automation.models';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { ServiceHealthCard } from './service-health-card';

describe('ServiceHealthCard', () => {
  let card: ServiceHealthCard;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ServiceHealthCard],
      providers: [
        provideRouter([]),
        {
          provide: ServiceHealthFacade,
          useValue: { startPolling: () => undefined, services: () => [], status: () => 'ready', error: () => '' },
        },
        { provide: SERVICE_LINK_BASES, useValue: {} },
      ],
    });
    card = TestBed.createComponent(ServiceHealthCard).componentInstance;
  });

  it('does not label degraded services as Healthy when latency is missing', () => {
    const degraded: AutomationService = {
      id: 'sonarr',
      name: 'Sonarr',
      status: 'degraded',
      detail: '33 missing',
      latencyMs: null,
    };
    expect(card.statusDetail(degraded)).toBe('33 missing');
    expect(card.statusDetail({ ...degraded, detail: '' })).toBe('Needs attention');
  });

  it('prefers latency for healthy services and falls back to detail then Healthy', () => {
    const healthy: AutomationService = {
      id: 'bazarr',
      name: 'Bazarr',
      status: 'healthy',
      detail: '0 wanted',
      latencyMs: 18,
    };
    expect(card.statusDetail(healthy)).toBe('18 ms');
    expect(card.statusDetail({ ...healthy, latencyMs: null })).toBe('0 wanted');
    expect(card.statusDetail({ ...healthy, latencyMs: null, detail: '' })).toBe('Healthy');
  });

  it('keeps degraded detail even when latency is present', () => {
    const degraded: AutomationService = {
      id: 'sonarr',
      name: 'Sonarr',
      status: 'degraded',
      detail: '33 missing',
      latencyMs: 40,
    };
    expect(card.statusDetail(degraded)).toBe('33 missing');
  });
});
