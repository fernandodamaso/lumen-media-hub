import { computed, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { applicationConfig, type Meta, type StoryObj } from '@storybook/angular';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { summarizeAutomationHealth } from '../automation/automation.models';
import { CalendarFacade } from '../calendar/calendar.facade';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { ActivityFacade } from './activity.facade';
import { RightRail } from './right-rail';

const meta: Meta = {
  title: 'Shell/RightRail',
  component: RightRail,
  tags: ['autodocs'],
  decorators: [
    applicationConfig({
      providers: [
        provideRouter([]),
        { provide: SERVICE_LINK_BASES, useValue: { sonarr: 'http://sonarr.local' } },
        {
          provide: CalendarFacade,
          useValue: {
            status: signal('ready'),
            events: signal([
              {
                id: 'ep-1',
                title: 'Duel of Suns',
                subtitle: 'S1E6 · Episode 6',
                time: '21:00',
                kind: 'episode',
                status: 'pending',
                airDate: new Date(Date.now() + 2 * 86_400_000).toISOString(),
                href: null,
              },
            ]),
            error: signal(''),
          },
        },
        {
          provide: ActivityFacade,
          useValue: {
            status: signal('ready'),
            items: signal([
              {
                id: 'radarr:91',
                source: 'radarr',
                kind: 'grabbed',
                title: 'Frontline (2026)',
                subtitle: '2.3 GB · 1080p',
                timestamp: new Date(Date.now() - 120_000).toISOString(),
                href: null,
              },
            ]),
            degradedSources: signal<string[]>([]),
            error: signal(''),
          },
        },
        {
          provide: ServiceHealthFacade,
          useValue: (() => {
            const summary = signal({
              generatedAt: '',
              services: [
                { id: 'sonarr', name: 'Sonarr', status: 'healthy' as const, detail: 'All systems operational', latencyMs: 12 },
                { id: 'jellyfin', name: 'Jellyfin', status: 'healthy' as const, detail: 'Streaming', latencyMs: 8 },
              ],
              problems: [],
              preview: [],
              availability: { services: 'present' as const, preview: 'empty' as const, problems: 'empty' as const },
            });
            return {
              services: computed(() => summary().services),
              health: computed(() => summarizeAutomationHealth(summary())),
              error: signal(''),
            };
          })(),
        },
      ],
    }),
  ],
  render: (args) => ({
    props: args,
    template: `<div style="width:296px;height:100vh"><mm-right-rail /></div>`,
  }),
};
export default meta;
type Story = StoryObj;

export const Default: Story = {};
