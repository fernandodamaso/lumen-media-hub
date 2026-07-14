import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { DownloadsBoard } from './downloads-board';
import { DownloadsAction, DownloadsFacade, DownloadsStatus } from './downloads.facade';
import { DownloadTorrent } from './media-stack-api';

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

  it('delegates pause/resume clicks and disables both controls while busy', () => {
    facade.status.set('ready');
    facade.torrents.set([{ id: 'a', name: 'A', state: 'downloading', progress: .5, size: 100, downloaded: 50, downloadRate: 10, uploadRate: 2, eta: 30, category: 'Uncategorized' }]);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('30s left');

    findButton('Pause all').click();
    expect(facade.runAction).toHaveBeenCalledWith('pause');
    facade.pendingAction.set('pause');
    fixture.detectChanges();
    expect(findButton('Pause all').disabled).toBe(true);
    expect(findButton('Resume all').disabled).toBe(true);
    expect(findButton('Pause all').getAttribute('aria-busy')).toBe('true');

    facade.pendingAction.set(null);
    facade.notice.set('All downloads paused.');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('All downloads paused.');
    findButton('Resume all').click();
    expect(facade.runAction).toHaveBeenCalledWith('resume');
  });

  it('renders error torrent state with a danger tone', () => {
    facade.status.set('ready');
    facade.torrents.set([{ id: 'a', name: 'Broken', state: 'error', progress: 12, size: 100, downloaded: 12, downloadRate: 0, uploadRate: 0, eta: 0, category: 'Movies' }]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.mm-status--danger')?.textContent).toContain('Error');
    expect(fixture.nativeElement.querySelector('.torrent-list')?.getAttribute('aria-live')).toBe('polite');
  });

  it('declares container-query compact layout for narrow dashboard tracks', () => {
    fixture.detectChanges();
    const styles = componentStyles();
    expect(styles).toContain('@container (max-width: 560px)');
    expect(styles).toMatch(/\.torrent-head[\s\S]*display:\s*flex/);
  });

  function findButton(label: string): HTMLButtonElement {
    return (Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[]).find((button) => button.textContent.includes(label)) as HTMLButtonElement;
  }
});

function createFacade() {
  const status = signal<DownloadsStatus>('loading');
  const torrents = signal<DownloadTorrent[]>([]);
  const error = signal('');
  const notice = signal('');
  const pendingAction = signal<DownloadsAction | null>(null);
  const refresh = vi.fn(async () => status.set('ready'));
  return {
    status,
    torrents,
    error,
    notice,
    pendingAction,
    summary: signal({ active: 1, total: 1, downloaded: 50, size: 100, downloadRate: 10, uploadRate: 2 }),
    startPolling: vi.fn(),
    refresh,
    runAction: vi.fn(),
  };
}

function componentStyles(): string {
  return Array.from(document.querySelectorAll('style'))
    .map((node) => node.textContent ?? '')
    .join('\n');
}
