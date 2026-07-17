import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { DownloadsBoard } from './downloads-board';
import { DownloadsAction, DownloadsFacade, DownloadsStatus } from './downloads.facade';
import { DownloadTorrent } from './downloads.models';

describe('DownloadsBoard', () => {
  let fixture: ComponentFixture<DownloadsBoard>;
  let facade: ReturnType<typeof createFacade>;

  beforeEach(() => {
    facade = createFacade();
    TestBed.configureTestingModule({
      imports: [DownloadsBoard],
      providers: [{ provide: DownloadsFacade, useValue: facade }],
    });
    fixture = TestBed.createComponent(DownloadsBoard);
  });

  it('renders loading, empty, and error states with retry recovery', async () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('.download-skeleton').length).toBeGreaterThan(0);

    facade.status.set('empty');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No active downloads');

    facade.status.set('error');
    facade.error.set('Offline');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Offline');
    findButton('Try again').click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(facade.refresh).toHaveBeenCalled();
    expect(facade.status()).toBe('ready');
  });

  it('delegates contextual pause/resume all', () => {
    facade.status.set('ready');
    facade.torrents.set([downloadingTorrent()]);
    facade.nextAction.set('pause');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('30s left');

    findButton('Pause all').click();
    expect(facade.runAction).toHaveBeenCalledWith('pause');

    facade.nextAction.set('resume');
    fixture.detectChanges();
    findButton('Resume all').click();
    expect(facade.runAction).toHaveBeenCalledWith('resume');
  });

  it('disables the action button while a bulk action is pending', () => {
    facade.status.set('ready');
    facade.torrents.set([downloadingTorrent()]);
    facade.nextAction.set('pause');
    fixture.detectChanges();

    facade.pendingAction.set('pause');
    fixture.detectChanges();
    expect(findButton('Pause all').disabled).toBe(true);
    expect(findButton('Pause all').getAttribute('aria-busy')).toBe('true');
  });

  it('delegates per-torrent pause/resume', () => {
    facade.status.set('ready');
    facade.torrents.set([downloadingTorrent()]);
    facade.nextAction.set('pause');
    fixture.detectChanges();

    const pauseButton = fixture.nativeElement.querySelector('.torrent-action') as HTMLButtonElement;
    expect(pauseButton).toBeTruthy();
    pauseButton.click();
    expect(facade.runTorrentAction).toHaveBeenCalledWith('a', 'pause');
  });

  it('renders seeding torrents in their own subsection', () => {
    facade.status.set('ready');
    facade.torrents.set([{ id: 'b', name: 'Seeded', state: 'seeding', progress: 100, size: 100, downloaded: 100, downloadRate: 0, uploadRate: 5, eta: 0, category: 'Movies' }]);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Seeding');
    expect(fixture.nativeElement.textContent).toContain('Complete');
  });

  it('keeps rows visible with a refresh notice after a background failure', () => {
    facade.status.set('ready');
    facade.torrents.set([downloadingTorrent()]);
    facade.error.set('Could not refresh downloads. Showing last loaded queue.');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Showing last loaded queue');
    expect(fixture.nativeElement.textContent).toContain('A');
    expect(fixture.nativeElement.querySelector('mm-state-card')).toBeNull();
  });

  it('declares container-query compact layout for narrow dashboard tracks', () => {
    fixture.detectChanges();
    const styles = componentStyles();
    expect(styles).toContain('@container (max-width: 420px)');
    expect(styles).toMatch(/\.torrent-head[\s\S]*display:\s*flex/);
  });

  function findButton(label: string): HTMLButtonElement {
    return (Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[]).find((button) => button.textContent?.includes(label)) as HTMLButtonElement;
  }
});

function createFacade() {
  const status = signal<DownloadsStatus>('loading');
  const torrents = signal<DownloadTorrent[]>([]);
  return {
    status,
    torrents,
    error: signal(''),
    notice: signal(''),
    pendingAction: signal<DownloadsAction | null>(null),
    pendingTorrentId: signal<string | null>(null),
    refreshing: signal(false),
    summary: signal({ active: 1, total: 1, downloaded: 50, size: 100, downloadRate: 10, uploadRate: 2 }),
    nextAction: signal<DownloadsAction | null>(null),
    canPauseAll: signal(false),
    canResumeAll: signal(false),
    startPolling: vi.fn(),
    refresh: vi.fn(async () => status.set('ready')),
    runAction: vi.fn(),
    runTorrentAction: vi.fn(),
  };
}

function downloadingTorrent(): DownloadTorrent {
  return { id: 'a', name: 'A', state: 'downloading', progress: 50, size: 100, downloaded: 50, downloadRate: 10, uploadRate: 2, eta: 30, category: 'Uncategorized' };
}

function componentStyles(): string {
  return Array.from(document.querySelectorAll('style'))
    .map((node) => node.textContent ?? '')
    .join('\n');
}
