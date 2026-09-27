import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import { fixtureHost } from '../../../testing/fixture-host';
import { MEDIA_STACK_API, MediaStackApi } from '../../media-stack/media-stack-api';
import { MmToastService } from '../../ui';
import { RequestableMediaItem, TvSeasonCollection } from '../media-request.models';
import { MediaRequestCompletion, MediaRequestDialog } from './media-request-dialog';

const movie: RequestableMediaItem = {
  identity: 'movie:42',
  type: 'movie',
  tmdbId: 42,
  title: 'Arrival',
  year: 2016,
  posterUrl: null,
  aiPickId: 'ai-movie-42',
};

const secondMovie: RequestableMediaItem = {
  identity: 'movie:43',
  type: 'movie',
  tmdbId: 43,
  title: 'Contact',
  year: 1997,
  posterUrl: null,
};

const show: RequestableMediaItem = {
  identity: 'tv:77',
  type: 'tv',
  tmdbId: 77,
  title: 'Signal House',
  year: 2024,
  posterUrl: null,
};

const tvSeasons: TvSeasonCollection = {
  tmdbId: 77,
  title: 'Signal House',
  seasons: [
    { seasonNumber: 2, name: 'Season 2', episodeCount: 10, airDate: '2025-04-11' },
    { seasonNumber: 0, name: 'Specials', episodeCount: 2, airDate: null },
    { seasonNumber: 1, name: 'Season 1', episodeCount: 8, airDate: '2024-03-01' },
  ],
};

function successAction() {
  return {
    ok: true,
    partial_success: false,
    jellyseerr_request_id: 812,
    request_status: 'requested' as const,
    already_requested: false,
    dashboard_state_persisted: true,
    reconciliation_queued: false,
    message: 'Request submitted to Jellyseerr.',
  };
}

describe('MediaRequestDialog', () => {
  let fixture: ComponentFixture<MediaRequestDialog>;
  let api: {
    getTvSeasons: ReturnType<typeof vi.fn<MediaStackApi['getTvSeasons']>>;
    requestMedia: ReturnType<typeof vi.fn<MediaStackApi['requestMedia']>>;
  };
  let toast: { show: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
      this.open = true;
    });
    HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
      this.open = false;
      this.dispatchEvent(new Event('close'));
    });
    api = {
      getTvSeasons: vi.fn(() => Promise.resolve(tvSeasons)),
      requestMedia: vi.fn(() => Promise.resolve(successAction())),
    };
    toast = { show: vi.fn() };
    TestBed.configureTestingModule({
      imports: [MediaRequestDialog],
      providers: [
        { provide: MEDIA_STACK_API, useValue: api as unknown as MediaStackApi },
        { provide: MmToastService, useValue: toast },
      ],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  async function render(item: RequestableMediaItem): Promise<HTMLElement> {
    fixture = TestBed.createComponent(MediaRequestDialog);
    fixture.componentRef.setInput('item', item);
    fixture.detectChanges();
    fixture.componentRef.setInput('opened', true);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixtureHost(fixture);
  }

  it('shows movie Add & search confirmation without loading seasons', async () => {
    const root = await render(movie);
    expect(root.textContent).toContain('Add Arrival and start searching for it?');
    expect(root.querySelector<HTMLElement>('[data-testid="media-request-submit"]')?.textContent).toContain(
      'Add & search',
    );
    expect(api.getTvSeasons).not.toHaveBeenCalled();
  });

  it('loads sorted TV metadata with regular seasons selected and specials off', async () => {
    const root = await render(show);
    expect(api.getTvSeasons).toHaveBeenCalledWith(77, expect.any(AbortSignal));
    const rows = [...root.querySelectorAll<HTMLElement>('[data-testid="media-request-season"]')];
    expect(rows.map((row) => row.textContent.replace(/\s+/g, ' ').trim())).toEqual([
      'Specials 2 episodes',
      'Season 1 8 episodes · 2024-03-01',
      'Season 2 10 episodes · 2025-04-11',
    ]);
    const checked = rows.map((row) => row.querySelector<HTMLInputElement>('input')?.checked);
    expect(checked).toEqual([false, true, true]);
  });

  it('disables TV submission when no seasons are selected or returned', async () => {
    let root = await render(show);
    for (const input of root.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')) {
      if (!input.checked) continue;
      input.checked = false;
      input.dispatchEvent(new Event('change'));
    }
    fixture.detectChanges();
    expect(
      root.querySelector<HTMLButtonElement>('[data-testid="media-request-submit"] button')?.disabled,
    ).toBe(true);

    fixture.destroy();
    api.getTvSeasons.mockResolvedValueOnce({ tmdbId: 77, title: 'Signal House', seasons: [] });
    root = await render(show);
    expect(root.textContent).toContain('No seasons are available to request.');
    expect(
      root.querySelector<HTMLButtonElement>('[data-testid="media-request-submit"] button')?.disabled,
    ).toBe(true);
  });

  it('sends exactly sorted selected TV seasons including user-selected specials', async () => {
    const root = await render(show);
    const rows = [...root.querySelectorAll<HTMLElement>('[data-testid="media-request-season"]')];
    const specials = rows[0].querySelector<HTMLInputElement>('input');
    const seasonOne = rows[1].querySelector<HTMLInputElement>('input');
    if (!specials || !seasonOne) throw new Error('season controls missing');
    specials.checked = true;
    specials.dispatchEvent(new Event('change'));
    seasonOne.checked = false;
    seasonOne.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    root.querySelector<HTMLButtonElement>('[data-testid="media-request-submit"] button')?.click();
    await fixture.whenStable();
    expect(api.requestMedia).toHaveBeenCalledWith({
      mediaType: 'tv',
      mediaId: 77,
      seasons: [0, 2],
    });
  });

  it('prevents duplicate submit while the request is busy', async () => {
    let resolveRequest!: (value: ReturnType<typeof successAction>) => void;
    api.requestMedia.mockImplementationOnce(
      () => new Promise((resolve) => {
        resolveRequest = resolve;
      }),
    );
    const root = await render(movie);
    const submit = root.querySelector<HTMLButtonElement>('[data-testid="media-request-submit"] button');
    submit?.click();
    submit?.click();
    expect(api.requestMedia).toHaveBeenCalledTimes(1);
    expect(fixture.componentInstance.busy()).toBe(true);
    resolveRequest(successAction());
    await fixture.whenStable();
  });

  it('closes, toasts, and emits completion only after success', async () => {
    const completed: MediaRequestCompletion[] = [];
    const root = await render(movie);
    fixture.componentInstance.completed.subscribe((event) => completed.push(event));
    root.querySelector<HTMLButtonElement>('[data-testid="media-request-submit"] button')?.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.componentInstance.opened()).toBe(false);
    expect(toast.show).toHaveBeenCalledWith('Request submitted', {
      body: 'Request submitted to Jellyseerr.',
      tone: 'success',
    });
    expect(completed).toEqual([
      {
        identity: 'movie:42',
        requestId: 812,
        status: 'requested',
        alreadyRequested: false,
      },
    ]);
  });

  it('keeps a newer dialog open when an older request resolves late', async () => {
    const pending = Promise.withResolvers<ReturnType<typeof successAction>>();
    api.requestMedia.mockReturnValueOnce(pending.promise);
    const completed: MediaRequestCompletion[] = [];
    const root = await render(movie);
    fixture.componentInstance.completed.subscribe((event) => completed.push(event));

    root.querySelector<HTMLButtonElement>('[data-testid="media-request-submit"] button')?.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.busy()).toBe(true);
    fixture.componentInstance.setOpened(false);
    expect(fixture.componentInstance.opened()).toBe(true);

    fixture.componentRef.setInput('opened', false);
    fixture.detectChanges();
    fixture.componentRef.setInput('item', secondMovie);
    fixture.componentRef.setInput('opened', true);
    fixture.detectChanges();

    pending.resolve(successAction());
    await Promise.resolve();
    await Promise.resolve();
    fixture.detectChanges();

    expect(fixture.componentInstance.item().identity).toBe('movie:43');
    expect(fixture.componentInstance.opened()).toBe(true);
    expect(toast.show).not.toHaveBeenCalled();
    expect(completed).toEqual([]);
  });

  it('surfaces partial success as a warning and still emits completion', async () => {
    api.requestMedia.mockResolvedValueOnce({
      ...successAction(),
      partial_success: true,
      dashboard_state_persisted: false,
      reconciliation_queued: false,
      message: 'Jellyseerr accepted the request; dashboard synchronization failed.',
    });
    const completed: MediaRequestCompletion[] = [];
    const root = await render(movie);
    fixture.componentInstance.completed.subscribe((event) => completed.push(event));

    root.querySelector<HTMLButtonElement>('[data-testid="media-request-submit"] button')?.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(toast.show).toHaveBeenCalledWith('Request submitted with a warning', {
      body: 'Jellyseerr accepted the request; dashboard synchronization failed.',
      tone: 'gold',
    });
    expect(completed).toHaveLength(1);
    expect(fixture.componentInstance.opened()).toBe(false);
  });

  it('keeps the dialog open with sanitized feedback on season-load and request failures', async () => {
    api.getTvSeasons.mockRejectedValueOnce(
      new Error('GET http://jellyseerr:5055 key=SECRET path=C:\\private'),
    );
    let root = await render(show);
    expect(fixture.componentInstance.opened()).toBe(true);
    expect(root.textContent).toContain('Seasons could not be loaded. Try again.');
    expect(root.textContent).not.toContain('SECRET');

    fixture.destroy();
    api.requestMedia.mockResolvedValueOnce({ ok: false, error: 'raw upstream SECRET path' });
    root = await render(movie);
    root.querySelector<HTMLButtonElement>('[data-testid="media-request-submit"] button')?.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.componentInstance.opened()).toBe(true);
    expect(root.textContent).toContain('This request could not be completed. Try again.');
    expect(root.textContent).not.toContain('SECRET');
    expect(toast.show).not.toHaveBeenCalled();
  });
});
