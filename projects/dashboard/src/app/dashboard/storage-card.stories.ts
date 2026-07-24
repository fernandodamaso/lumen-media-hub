import { computed, signal } from '@angular/core';
import { type Meta, type StoryObj } from '@storybook/angular';
import { StorageFacade, StorageStatus } from '../storage/storage.facade';
import { StorageOverview } from '../storage/storage.models';
import { StorageCard } from './storage-card';

function createFacade(status: StorageStatus, volumes: StorageOverview['volumes'], error = '') {
  const overview = signal<StorageOverview | null>(volumes.length ? { generatedAt: new Date().toISOString(), volumes } : null);
  return {
    status: signal<StorageStatus>(status),
    overview,
    volumes: computed(() => overview()?.volumes ?? []),
    error: signal(error),
    startPolling: () => {},
    refresh: async () => {},
  };
}

const meta: Meta<StorageCard> = {
  title: 'Dashboard/StorageCard',
  component: StorageCard,
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<StorageCard>;

const volumes: StorageOverview['volumes'] = [
  { id: 'media', label: 'Media library', kind: 'library', usedBytes: 4.8 * 1024 ** 4, totalBytes: 7.2 * 1024 ** 4 },
  { id: 'downloads', label: 'Downloads', kind: 'downloads', usedBytes: 324 * 1024 ** 3, totalBytes: 1 * 1024 ** 4 },
  { id: 'cache', label: 'Cache & temp', kind: 'cache', usedBytes: 68 * 1024 ** 3, totalBytes: 500 * 1024 ** 3 },
];

export const Default: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [{ provide: StorageFacade, useValue: createFacade('ready', volumes) }],
    },
    template: `<div style="max-width:380px"><mm-storage-card /></div>`,
  }),
};

export const Loading: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [{ provide: StorageFacade, useValue: createFacade('loading', []) }],
    },
    template: `<div style="max-width:380px"><mm-storage-card /></div>`,
  }),
};

export const ErrorState: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [{ provide: StorageFacade, useValue: createFacade('error', [], 'Storage is temporarily unavailable. Try again.') }],
    },
    template: `<div style="max-width:380px"><mm-storage-card /></div>`,
  }),
};

export const Empty: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [{ provide: StorageFacade, useValue: createFacade('ready', []) }],
    },
    template: `<div style="max-width:380px"><mm-storage-card /></div>`,
  }),
};
