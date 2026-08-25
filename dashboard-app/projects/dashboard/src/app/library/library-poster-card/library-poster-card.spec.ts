import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { fixtureHost } from '../../../testing/fixture-host';
import { MmToastService } from '@app/ui';
import { LibraryDeletePreview, LibraryItem } from '../library.models';
import { LibraryItemsFacade } from '../library-items.facade';
import { LibraryPosterCard } from './library-poster-card';

describe('LibraryPosterCard', () => {
  let fixture: ComponentFixture<LibraryPosterCard>;
  let facade: {
    setPlayed: ReturnType<typeof vi.fn<LibraryItemsFacade['setPlayed']>>;
    previewDeletion: ReturnType<typeof vi.fn<LibraryItemsFacade['previewDeletion']>>;
    deleteItem: ReturnType<typeof vi.fn<LibraryItemsFacade['deleteItem']>>;
  };
  let toast: { show: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    facade = {
      setPlayed: vi.fn().mockResolvedValue(undefined),
      previewDeletion: vi.fn(),
      deleteItem: vi.fn(),
    };
    toast = { show: vi.fn() };
    TestBed.configureTestingModule({
      imports: [LibraryPosterCard],
      providers: [
        { provide: LibraryItemsFacade, useValue: facade },
        { provide: MmToastService, useValue: toast },
      ],
    });
    fixture = TestBed.createComponent(LibraryPosterCard);
    fixture.componentRef.setInput('item', movieItem({ played: false }));
    fixture.componentRef.setInput('href', 'https://jellyfin.example/item');
    fixture.detectChanges();
  });

  it('updates watched pressed state only after the facade resolves', async () => {
    let resolvePlayed: (() => void) | undefined;
    facade.setPlayed.mockImplementation(() => {
      return new Promise<void>((resolve) => {
        resolvePlayed = () => {
          fixture.componentRef.setInput('item', movieItem({ played: true }));
          resolve();
        };
      });
    });
    const button = fixtureHost(fixture).querySelector(
      'button[aria-label="Mark watched"]',
    ) as HTMLButtonElement;
    button.click();
    fixture.detectChanges();
    expect(button.getAttribute('aria-pressed')).toBe('false');

    resolvePlayed?.();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(facade.setPlayed).toHaveBeenCalledWith('m1', true);
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(toast.show).toHaveBeenCalledWith('Marked as watched', { tone: 'success' });
  });

  it('uses the manager detail link for the poster and title while keeping Jellyfin play separate', () => {
    fixture.componentRef.setInput('detailsHref', 'https://sonarr.example/series/the-bear');
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const poster = root.querySelector('.mm-media-card__hit') as HTMLAnchorElement;
    const title = root.querySelector('.library-poster-card__title-link') as HTMLAnchorElement;
    const play = root.querySelector('a[aria-label="Play Moonrise"]') as HTMLAnchorElement;

    expect(poster.href).toBe('https://sonarr.example/series/the-bear');
    expect(poster.target).toBe('_blank');
    expect(poster.rel).toBe('noreferrer');
    expect(title.href).toBe('https://sonarr.example/series/the-bear');
    expect(title.target).toBe('_blank');
    expect(title.rel).toBe('noreferrer');
    expect(play.href).toBe('https://jellyfin.example/item');
  });

  it('keeps watched state and toasts on failure', async () => {
    facade.setPlayed.mockRejectedValue(new Error('fail'));
    const button = fixtureHost(fixture).querySelector(
      'button[aria-label="Mark watched"]',
    ) as HTMLButtonElement;
    button.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(button.getAttribute('aria-pressed')).toBe('false');
    expect(toast.show).toHaveBeenCalledWith('Could not update watched state', { tone: 'error' });
  });

  it('does not open the dialog when preview fails', async () => {
    facade.previewDeletion.mockRejectedValue(new Error('fail'));
    const button = fixtureHost(fixture).querySelector(
      'button[aria-label="Delete"]',
    ) as HTMLButtonElement;
    button.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('dialog[open]')).toBeNull();
    expect(toast.show).toHaveBeenCalledWith('Could not prepare deletion', { tone: 'error' });
  });

  it('closes the dialog and clears preview when delete confirmation fails', async () => {
    const preview: LibraryDeletePreview = {
      previewId: 'preview-1',
      title: 'Moonrise',
      kind: 'movie',
      manager: 'Radarr',
      episodeCount: null,
      torrentCount: 1,
      expiresAt: new Date().toISOString(),
    };
    facade.previewDeletion.mockResolvedValue(preview);
    facade.deleteItem.mockRejectedValue(new Error('fail'));
    (
      fixtureHost(fixture).querySelector('button[aria-label="Delete"]') as HTMLButtonElement
    ).click();
    await fixture.whenStable();
    fixture.detectChanges();
    (
      fixtureHost(fixture).querySelector('mm-button[label="Delete media"] button') as HTMLButtonElement
    ).click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('dialog[open]')).toBeNull();
    expect(toast.show).toHaveBeenCalledWith('Could not delete this title', { tone: 'error' });
  });

  it('toasts success after a completed delete', async () => {
    const preview: LibraryDeletePreview = {
      previewId: 'preview-1',
      title: 'Moonrise',
      kind: 'movie',
      manager: 'Radarr',
      episodeCount: null,
      torrentCount: 1,
      expiresAt: new Date().toISOString(),
    };
    facade.previewDeletion.mockResolvedValue(preview);
    facade.deleteItem.mockResolvedValue({
      ok: true,
      removed: true,
      torrentCount: 1,
      jellyfinRefresh: 'ok',
      steps: { torrents: 'ok', library: 'ok', jellyfin: 'ok' },
    });
    (
      fixtureHost(fixture).querySelector('button[aria-label="Delete"]') as HTMLButtonElement
    ).click();
    await fixture.whenStable();
    fixture.detectChanges();
    (
      fixtureHost(fixture).querySelector('mm-button[label="Delete media"] button') as HTMLButtonElement
    ).click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(toast.show).toHaveBeenCalledWith('Removed Moonrise', {
      body: 'Deleted from Radarr and qBittorrent.',
      tone: 'success',
    });
  });

  it('does not delete when cancel is clicked', async () => {
    const preview: LibraryDeletePreview = {
      previewId: 'preview-1',
      title: 'Moonrise',
      kind: 'movie',
      manager: 'Radarr',
      episodeCount: null,
      torrentCount: 1,
      expiresAt: new Date().toISOString(),
    };
    facade.previewDeletion.mockResolvedValue(preview);
    (
      fixtureHost(fixture).querySelector('button[aria-label="Delete"]') as HTMLButtonElement
    ).click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('.library-poster-card__delete-title')?.textContent).toBe(
      'Moonrise',
    );
    (
      fixtureHost(fixture).querySelector('mm-button[label="Cancel"] button') as HTMLButtonElement
    ).click();
    fixture.detectChanges();
    expect(facade.deleteItem).not.toHaveBeenCalled();
  });
});

function movieItem(overrides: Partial<LibraryItem> = {}): LibraryItem {
  return {
    id: 'm1',
    title: 'Moonrise',
    kind: 'movie',
    meta: '2024 · Movie',
    art: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
    overview: '',
    href: null,
    artworkState: 'ok',
    playable: true,
    episodeCount: null,
    played: false,
    ...overrides,
  };
}
