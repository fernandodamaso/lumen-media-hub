import { computed, signal } from '@angular/core';
import { type Meta, type StoryObj } from '@storybook/angular';
import { AutomationSummary } from '../automation/automation.models';
import { ServiceHealthFacade, ServiceHealthStatus } from '../automation/service-health.facade';
import { ServiceHealthCard } from './service-health-card';

function createFacade(status: ServiceHealthStatus, services: AutomationSummary['services'], error = '') {
  const summary = signal<AutomationSummary | null>(
    services.length
      ? {
          generatedAt: new Date().toISOString(),
          services,
          preview: [],
          problems: services
            .filter((service) => service.status === 'degraded' || service.status === 'down')
            .map((service) => ({
              id: service.id,
              summary: `${service.name} issue`,
              serviceId: service.id,
              severity: 'actionable' as const,
            })),
          availability: { services: 'present', preview: 'empty', problems: 'present' },
        }
      : null,
  );
  return {
    status: signal<ServiceHealthStatus>(status),
    summary,
    services: computed(() => summary()?.services ?? []),
    problems: computed(() => summary()?.problems ?? []),
    generatedAt: computed(() => summary()?.generatedAt ?? ''),
    health: computed(() => ({ overall: 'unknown' as const, actionableCount: 0 })),
    error: signal(error),
    startPolling: () => {},
    refresh: async () => {},
  };
}

const meta: Meta<ServiceHealthCard> = {
  title: 'Dashboard/ServiceHealthCard',
  component: ServiceHealthCard,
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<ServiceHealthCard>;

const healthyServices: AutomationSummary['services'] = [
  { id: 'jellyfin', name: 'Jellyfin', status: 'healthy', detail: '', latencyMs: 18 },
  { id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: '', latencyMs: 20 },
  { id: 'radarr', name: 'Radarr', status: 'healthy', detail: '', latencyMs: 22 },
  { id: 'prowlarr', name: 'Prowlarr', status: 'degraded', detail: '2 warnings', latencyMs: 350 },
  { id: 'sabnzbd', name: 'SABnzbd', status: 'down', detail: 'Last seen 18m ago' },
  { id: 'qbittorrent', name: 'qBittorrent', status: 'healthy', detail: '', latencyMs: 15 },
  { id: 'bazarr', name: 'Bazarr', status: 'healthy', detail: '', latencyMs: 16 },
  { id: 'unpackerr', name: 'Unpackerr', status: 'healthy', detail: '', latencyMs: 24 },
];

export const Default: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [{ provide: ServiceHealthFacade, useValue: createFacade('ready', healthyServices) }],
    },
    template: `<div style="max-width:380px"><mm-service-health-card /></div>`,
  }),
};

export const Loading: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [{ provide: ServiceHealthFacade, useValue: createFacade('loading', []) }],
    },
    template: `<div style="max-width:380px"><mm-service-health-card /></div>`,
  }),
};

export const Error: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [{ provide: ServiceHealthFacade, useValue: createFacade('error', [], 'Service health is temporarily unavailable. Try again.') }],
    },
    template: `<div style="max-width:380px"><mm-service-health-card /></div>`,
  }),
};

export const Empty: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [{ provide: ServiceHealthFacade, useValue: createFacade('ready', []) }],
    },
    template: `<div style="max-width:380px"><mm-service-health-card /></div>`,
  }),
};
