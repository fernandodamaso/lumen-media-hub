import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { applicationConfig, type Meta, type StoryObj } from '@storybook/angular';
import { AutomationFacade } from '../automation/automation.facade';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { CalendarFacade } from '../calendar/calendar.facade';
import { DownloadsFacade } from '../downloads/downloads.facade';
import { LibraryStatsFacade } from '../library/library-stats.facade';
import { LibraryItemsFacade } from '../library/library-items.facade';
import { WatchNextFacade } from '../library/watch-next.facade';
import { JELLYFIN_LINK_BASES } from '../library/library.models';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { ActivityFacade } from '../right-rail/activity.facade';
import { StorageFacade } from '../storage/storage.facade';
import { TrendingFacade } from '../dashboard/trending.facade';
import { CommandPalette } from './command-palette';

const empty = { refresh: () => Promise.resolve() };

const meta: Meta<CommandPalette> = {
  title: 'Shell/CommandPalette',
  component: CommandPalette,
  tags: ['autodocs'],
  args: { open: true },
  decorators: [
    applicationConfig({
      providers: [
        provideRouter([]),
        { provide: JELLYFIN_LINK_BASES, useValue: { jellyfinBase: '' } },
        { provide: SERVICE_LINK_BASES, useValue: { qbittorrent: '' } },
        { provide: MEDIA_STACK_API, useValue: { listWatchNext: () => Promise.resolve({ items: [] }) } },
        { provide: LibraryItemsFacade, useValue: { items: signal([]), refresh: empty.refresh } },
        { provide: WatchNextFacade, useValue: { items: signal([]), refresh: empty.refresh } },
        { provide: ServiceHealthFacade, useValue: empty },
        { provide: LibraryStatsFacade, useValue: empty },
        { provide: DownloadsFacade, useValue: { ...empty, runAction: empty.refresh } },
        { provide: StorageFacade, useValue: empty },
        { provide: CalendarFacade, useValue: empty },
        { provide: AutomationFacade, useValue: empty },
        { provide: ActivityFacade, useValue: empty },
        { provide: TrendingFacade, useValue: empty },
      ],
    }),
  ],
};

export default meta;
type Story = StoryObj<CommandPalette>;

export const Default: Story = {
  play: ({ canvasElement }) => {
    const dialog = canvasElement.querySelector('dialog');
    const input = canvasElement.querySelector('input[aria-label="Search commands"]');
    if (!dialog || !input) throw new Error('Command palette dialog or search input was not rendered');
    if (dialog.getAttribute('aria-label') !== 'Command palette') throw new Error('Dialog name is missing');
  },
};
