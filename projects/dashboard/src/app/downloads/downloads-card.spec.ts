import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { DownloadsCard } from './downloads-card';
import { DownloadsAction, DownloadsFacade, DownloadsStatus } from './downloads.facade';
import { DownloadTorrent } from './downloads.models';

describe('DownloadsCard', () => {
  let fixture: ComponentFixture<DownloadsCard>;
  let facade: ReturnType<typeof createFacade>;

  beforeEach(() => {
    facade = createFacade();
    TestBed.configureTestingModule({
      imports: [DownloadsCard],
      providers: [{ provide: DownloadsFacade, useValue: facade }],
    });
    fixture = TestBed.createComponent(DownloadsCard);
  });

  it('renders loading, empty, and error states with retry recovery', async () => {
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    expect(root.querySelectorAll('.download-skeleton').length).toBeGreaterThan(0);

    facade.status.set('empty');
    fixture.detectChanges();
    expect(root.textContent).toContain('No active downloads');

    facade.status.set('error');
    facade.error.set('Offline');
    fixture.detectChanges();
    expect(root.textContent).toContain('Offline');
    findButton('Try again').click();
    await fixture.whenStable();
    expect(facade.refresh).toHaveBeenCalled();
    expect(facade.status()).toBe('ready');
  });

  it('hides rate stats and actions in the empty state', () => {
    facade.status.set('empty');
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    expect(root.querySelector('.dl-stats')).toBeNull();
    expect(root.querySelector('.mm-state-card--centered')).toBeTruthy();
    expect(root.textContent).not.toContain('Pause all');

    facade.status.set('ready');
    facade.torrents.set([downloadingTorrent()]);
    fixture.detectChanges();
    expect(root.querySelector('.dl-stats')).toBeTruthy();
  });

  it('shows rate stats and delegates pause/resume all', () => {
    facade.status.set('ready');
    facade.torrents.set([downloadingTorrent()]);
    facade.canPauseAll.set(true);
    facade.summary.set({
      active: 1,
      total: 1,
      downloaded: 50,
      size: 100,
      downloadRate: 10 * 1024 * 1024,
      uploadRate: 2 * 1024 * 1024,
    });
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('Down');
    expect(root.textContent).toContain('Up');
    expect(root.textContent).toContain('30s left');

    findButton('Pause all').click();
    expect(facade.runAction).toHaveBeenCalledWith('pause');

    facade.canPauseAll.set(false);
    facade.canResumeAll.set(true);
    fixture.detectChanges();
    findButton('Resume all').click();
    expect(facade.runAction).toHaveBeenCalledWith('resume');
  });

  it('delegates per-torrent pause/resume', () => {
    facade.status.set('ready');
    facade.torrents.set([downloadingTorrent()]);
    facade.canPauseAll.set(true);
    fixture.detectChanges();

    const pauseButton = fixtureHost(fixture).querySelector('mm-icon-button button') as HTMLButtonElement;
    pauseButton.click();
    expect(facade.runTorrentAction).toHaveBeenCalledWith('a', 'pause');
  });

  function findButton(label: string): HTMLButtonElement {
    const match = [...fixtureHost(fixture).querySelectorAll('button')].find((button) =>
      button.textContent.includes(label),
    );
    if (!match) throw new Error(`Button not found: ${label}`);
    return match;
  }
});

function createFacade() {
  const status = signal<DownloadsStatus>('loading');
  return {
    status,
    torrents: signal<DownloadTorrent[]>([]),
    error: signal(''),
    notice: signal(''),
    pendingAction: signal<DownloadsAction | null>(null),
    pendingTorrentId: signal<string | null>(null),
    refreshing: signal(false),
    summary: signal({ active: 0, total: 0, downloaded: 0, size: 0, downloadRate: 0, uploadRate: 0 }),
    nextAction: signal<DownloadsAction | null>(null),
    canPauseAll: signal(false),
    canResumeAll: signal(false),
    startPolling: vi.fn(),
    refresh: vi.fn(() => {
      status.set('ready');
      return Promise.resolve();
    }),
    runAction: vi.fn(),
    runTorrentAction: vi.fn(),
  };
}

function downloadingTorrent(): DownloadTorrent {
  return {
    id: 'a',
    name: 'A',
    state: 'downloading',
    progress: 50,
    size: 100,
    downloaded: 50,
    downloadRate: 10,
    uploadRate: 2,
    eta: 30,
    category: 'Uncategorized',
  };
}
