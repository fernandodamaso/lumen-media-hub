import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { applicationConfig, type Meta, type StoryObj } from '@storybook/angular';
import { ServiceHealthFacade } from '../../automation/service-health.facade';
import { DownloadsFacade } from '../../downloads/downloads.facade';
import { LibraryStatsFacade } from '../../library/library-stats.facade';
import { WatchNextFacade } from '../../library/watch-next.facade';
import { StorageFacade } from '../../storage/storage.facade';
import { StatStrip } from './stat-strip';

function providers(status: 'ready' | 'loading') {
  const loading = status === 'loading';
  return [
    provideRouter([]),
    {
      provide: LibraryStatsFacade,
      useValue: {
        status: signal(status),
        stats: signal(loading ? null : { movies: 428, series: 76, availability: 'complete' as const }),
      },
    },
    {
      provide: DownloadsFacade,
      useValue: {
        status: signal(status),
        summary: signal({ active: 2, total: 2, downloaded: 50, size: 100, downloadRate: 690_000, uploadRate: 120_000 }),
      },
    },
    { provide: WatchNextFacade, useValue: { status: signal(status), totalCount: signal(8) } },
    {
      provide: StorageFacade,
      useValue: {
        status: signal(status),
        volumes: signal(
          loading
            ? []
            : [{ id: 'media', label: 'Media library', kind: 'library' as const, usedBytes: 229.4 * 1024 ** 3, totalBytes: 447.1 * 1024 ** 3 }],
        ),
      },
    },
    {
      provide: ServiceHealthFacade,
      useValue: {
        status: signal(status),
        services: signal(
          loading
            ? []
            : [
                { id: 'sonarr', name: 'Sonarr', status: 'healthy' as const, detail: '', latencyMs: 10 },
                { id: 'radarr', name: 'Radarr', status: 'healthy' as const, detail: '', latencyMs: 12 },
              ],
        ),
        health: signal({ overall: 'healthy' as const, actionableCount: 0 }),
      },
    },
  ];
}

const meta: Meta = {
  title: 'Dashboard/StatStrip',
  component: StatStrip,
  tags: ['autodocs'],
};
export default meta;
type Story = StoryObj;

export const Ready: Story = {
  decorators: [applicationConfig({ providers: providers('ready') })],
};

export const Loading: Story = {
  decorators: [applicationConfig({ providers: providers('loading') })],
};
