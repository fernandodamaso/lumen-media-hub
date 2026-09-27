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
import { MediaSearchItem } from '../media-request/media-request.models';

const empty = { refresh: () => Promise.resolve() };
const lifecycleItems: MediaSearchItem[] = [
  {
    identity: 'movie:501001', type: 'movie', tmdbId: 501001, title: 'Demo Available', year: 2024,
    overview: 'Available in the local library.', posterUrl: null, status: 'available', service: 'jellyfin',
    serviceHref: 'https://jellyfin.example/item/501001', requestId: null, monitored: null, jellyfinId: 'jf-501001',
  },
  {
    identity: 'movie:501002', type: 'movie', tmdbId: 501002, title: 'Demo Requested', year: 2025,
    overview: 'Already requested.', posterUrl: null, status: 'requested', service: null,
    serviceHref: null, requestId: 9201, monitored: null,
  },
  {
    identity: 'tv:501003', type: 'tv', tmdbId: 501003, title: 'Demo Processing', year: 2025,
    overview: 'Acquisition is active.', posterUrl: null, status: 'processing', service: null,
    serviceHref: null, requestId: 9202, monitored: null,
  },
  {
    identity: 'movie:501004', type: 'movie', tmdbId: 501004, title: 'Demo Tracked', year: 2023,
    overview: 'Tracked in Radarr.', posterUrl: null, status: 'tracked', service: 'radarr',
    serviceHref: 'https://radarr.example/movie/501004', requestId: null, monitored: true,
  },
  {
    identity: 'tv:501005', type: 'tv', tmdbId: 501005, title: 'Demo Missing', year: 2024,
    overview: 'Ready to request.', posterUrl: null, status: 'missing', service: null,
    serviceHref: null, requestId: null, monitored: null,
  },
  {
    identity: 'movie:501006', type: 'movie', tmdbId: 501006, title: 'Demo Unknown', year: null,
    overview: 'Lifecycle providers are unavailable.', posterUrl: null, status: 'unknown', service: null,
    serviceHref: null, requestId: null, monitored: null,
  },
];

const storyApi = {
  listWatchNext: () => Promise.resolve({ items: [] }),
  searchMedia: (query: string) => Promise.resolve(query === 'unavailable'
    ? {
        ok: false as const,
        availability: 'unavailable' as const,
        sources: { jellyseerr: 'unavailable' as const },
        items: [],
        error: 'Media search is temporarily unavailable',
      }
    : {
        ok: true as const,
        availability: 'available' as const,
        sources: { jellyseerr: 'fresh' as const },
        items: lifecycleItems,
      }),
  getTvSeasons: () => Promise.resolve({ tmdbId: 501005, title: 'Demo Missing', seasons: [] }),
  requestMedia: () => Promise.resolve({ ok: false as const, error: 'Story request disabled' }),
};

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
        { provide: MEDIA_STACK_API, useValue: storyApi },
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

    const focusables = dialog.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
    );
    if (focusables.length < 2) throw new Error('expected at least two focusable elements in the palette');
    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    last.focus();
    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }));
    if (document.activeElement !== first) throw new Error('Tab did not wrap to the first focusable element');

    first.focus();
    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }));
    if (document.activeElement !== last) throw new Error('Shift+Tab did not wrap to the last focusable element');
  },
};

export const LifecycleResults: Story = {
  play: async ({ canvasElement }) => {
    const input = canvasElement.querySelector<HTMLInputElement>('input[aria-label="Search commands"]');
    if (!input) throw new Error('Command palette search input was not rendered');
    input.value = 'demo';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 300));
    if (!canvasElement.textContent.includes('Your Library')) throw new Error('Your Library group is missing');
    if (!canvasElement.textContent.includes('Catalog')) throw new Error('Catalog group is missing');
    if (!canvasElement.textContent.includes('Demo Processing')) throw new Error('Lifecycle results are missing');
  },
};

export const CatalogUnavailable: Story = {
  play: async ({ canvasElement }) => {
    const input = canvasElement.querySelector<HTMLInputElement>('input[aria-label="Search commands"]');
    if (!input) throw new Error('Command palette search input was not rendered');
    input.value = 'unavailable';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 300));
    const status = canvasElement.querySelector('[data-testid="palette-search-status"]');
    if (!status?.textContent.includes('temporarily unavailable')) {
      throw new Error('Unavailable live-region state is missing');
    }
  },
};
