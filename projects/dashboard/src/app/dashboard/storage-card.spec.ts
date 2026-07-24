import { computed, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { StorageFacade, StorageStatus } from '../storage/storage.facade';
import { StorageOverview } from '../storage/storage.models';
import { StorageCard } from './storage-card';

describe('StorageCard', () => {
  it('renders MmProgress for each volume', () => {
    const overview = signal<StorageOverview | null>({
      generatedAt: new Date().toISOString(),
      volumes: [
        { id: 'media', label: 'Media library', kind: 'library', usedBytes: 50, totalBytes: 100 },
        { id: 'downloads', label: 'Downloads', kind: 'downloads', usedBytes: 25, totalBytes: 100 },
      ],
    });
    const facade = {
      status: signal<StorageStatus>('ready'),
      overview,
      volumes: computed(() => overview()?.volumes ?? []),
      error: signal(''),
      startPolling: () => {},
      refresh: async () => {},
    };

    TestBed.configureTestingModule({
      imports: [StorageCard],
      providers: [{ provide: StorageFacade, useValue: facade }],
    });
    const fixture = TestBed.createComponent(StorageCard);
    fixture.detectChanges();

    const bars = fixtureHost(fixture).querySelectorAll('[role="progressbar"]');
    expect(bars).toHaveLength(2);
    expect(bars[0].getAttribute('aria-valuenow')).toBe('50');
    expect(fixtureHost(fixture).querySelector('.mm-progress--premiere')).toBeTruthy();
    expect(fixtureHost(fixture).querySelector('.mm-progress--info')).toBeTruthy();
  });
});
