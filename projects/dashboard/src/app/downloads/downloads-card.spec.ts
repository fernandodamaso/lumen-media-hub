import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { DownloadsCard } from './downloads-card';
import { DownloadsAction, DownloadsFacade, DownloadsStatus } from './downloads.facade';
import { DownloadTorrent, TorrentState } from './downloads.models';

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

  it('shows dl-stats during loading and ready, hides on empty', () => {
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    expect(root.querySelector('.dl-stats')).toBeTruthy();

    facade.status.set('empty');
    fixture.detectChanges();
    expect(root.querySelector('.dl-stats')).toBeNull();

    facade.status.set('ready');
    facade.torrents.set([downloadingTorrent()]);
    fixture.detectChanges();
    expect(root.querySelector('.dl-stats')).toBeTruthy();
  });

  it('renders header stat value and unit separately', () => {
    facade.status.set('ready');
    facade.torrents.set([downloadingTorrent()]);
    facade.summary.set({
      active: 1, total: 1, downloaded: 50, size: 100,
      downloadRate: 10 * 1024 * 1024,
      uploadRate: 2 * 1024 * 1024,
    });
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    const nums = root.querySelectorAll<HTMLElement>('.dl-stat .num');
    const units = root.querySelectorAll<HTMLElement>('.dl-stat__unit');
    expect(nums).toHaveLength(2);
    expect(units).toHaveLength(2);
    expect(nums[0].textContent).toContain('10.0');
    expect(units[0].textContent).toContain('MB/s');
    expect(nums[1].textContent).toContain('2.0');
    expect(units[1].textContent).toContain('MB/s');
  });

  it.each([
    ['downloading', 'pill--accent'],
    ['seeding', 'pill--green'],
    ['paused', 'pill--amber'],
    ['queued', 'pill--amber'],
    ['checking', 'pill--amber'],
    ['error', 'pill--danger'],
  ])('renders .%s for %s state', (state, expectedClass) => {
    facade.status.set('ready');
    facade.torrents.set([{ ...downloadingTorrent(), id: state, state: state as TorrentState }]);
    fixture.detectChanges();
    const pill = fixtureHost(fixture).querySelector('.pill');
    expect(pill).toBeTruthy();
    expect((pill as HTMLElement).classList.contains(expectedClass)).toBe(true);
  });

  it('applies live shimmer class on mm-progress only for downloading torrents', () => {
    facade.status.set('ready');
    facade.torrents.set([downloadingTorrent()]);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('.mm-progress__bar--live')).toBeTruthy();

    facade.torrents.set([{ ...downloadingTorrent(), id: 's', state: 'seeding' }]);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('.mm-progress__bar--live')).toBeNull();

    facade.torrents.set([{ ...downloadingTorrent(), id: 'p', state: 'paused' }]);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('.mm-progress__bar--live')).toBeNull();
  });

  it.each([
    ['seeding', 'dl-item--seeding'],
    ['paused', 'dl-item--paused'],
    ['queued', 'dl-item--queued'],
    ['checking', 'dl-item--checking'],
    ['error', 'dl-item--error'],
  ])('renders .%s for %s state', (state, expectedClass) => {
    facade.status.set('ready');
    facade.torrents.set([{ ...downloadingTorrent(), id: state, state: state as TorrentState }]);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector(`.${expectedClass}`)).toBeTruthy();
  });

  it('renders meta with size text and rates grouped in meta-rates', () => {
    facade.status.set('ready');
    facade.torrents.set([downloadingTorrent()]);
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    const meta = root.querySelector('.dl-item__meta');
    expect(meta).not.toBeNull();
    expect((meta as Element).children).toHaveLength(2);

    const firstSpan = (meta as Element).children[0] as HTMLElement;
    expect(firstSpan.textContent).toMatch(/50\s*B/);
    expect(firstSpan.textContent).toMatch(/100\s*B/);

    const metaRates = (meta as Element).querySelector('.meta-rates');
    expect(metaRates).not.toBeNull();
    expect((metaRates as Element).textContent).toMatch(/10\s*B\/s/);
    expect((metaRates as Element).textContent).toMatch(/2\s*B\/s/);
    expect((metaRates as Element).textContent).toContain('30s left');

    facade.torrents.set([{ ...downloadingTorrent(), id: 'b', eta: 0 }]);
    fixture.detectChanges();
    expect(root.querySelector('.meta-rates')?.textContent).toContain('Complete');
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
    summary: signal({ active: 0, total: 0, downloaded: 0, size: 0, downloadRate: 0, uploadRate: 0 }), // ponytail: mock doesn't derive summary from torrents; component specs verify rendering, facade specs verify derivation
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
