import { ComponentFixture, TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { DiscoverCard } from './discover-card';
import { DiscoverCardItem } from './discover-format';

describe('DiscoverCard', () => {
  let fixture: ComponentFixture<DiscoverCard>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [DiscoverCard] }).compileComponents();
    fixture = TestBed.createComponent(DiscoverCard);
  });

  it('renders backend lifecycle actions with durable explanations', () => {
    setItem({ tmdbId: 0, title: 'Untitled' });
    expect(requestButton().textContent).toContain('No TMDB ID');
    expect(requestButton().disabled).toBe(true);
    expect(requestWrapper().title).toContain('missing TMDB id');

    setItem({ tmdbId: 1, mediaStatus: 'available', service: 'jellyfin', serviceHref: 'https://jellyfin.example/item/1', title: 'Owned' });
    expect(requestButton().textContent).toContain('Open in Jellyfin');
    expect(requestWrapper().title).toContain('Open in Jellyfin');

    setItem({ tmdbId: 1, mediaStatus: 'requested', title: 'Queued' });
    expect(requestButton().textContent).toContain('Requested');

    setItem({ tmdbId: 1, mediaStatus: 'processing', title: 'Downloading' });
    expect(requestButton().textContent).toContain('Processing');

    setItem({ tmdbId: 1, mediaStatus: 'unknown', title: 'Unclear' });
    expect(requestButton().textContent).toContain('Status unavailable');
    expect(requestButton().disabled).toBe(true);
  });

  it('emits the server-derived open or request action', () => {
    const actions: unknown[] = [];
    fixture.componentInstance.request.subscribe((action) => actions.push(action));

    setItem({
      title: 'Tracked',
      mediaStatus: 'tracked',
      service: 'sonarr',
      serviceHref: 'https://sonarr.example/series/1',
    });
    requestButton().click();
    setItem({ title: 'Missing', mediaStatus: 'missing', service: null, serviceHref: null });
    requestButton().click();

    expect(actions).toEqual([
      expect.objectContaining({ intent: 'open', href: 'https://sonarr.example/series/1' }),
      expect.objectContaining({ intent: 'request' }),
    ]);
  });

  it('emits feedback without invoking request', () => {
    setItem({ tmdbId: 1, title: 'Eligible' });
    fixture.componentRef.setInput('showFeedback', true);
    fixture.detectChanges();

    const feedback: string[] = [];
    let requestCount = 0;
    fixture.componentInstance.feedback.subscribe((value) => feedback.push(value));
    fixture.componentInstance.request.subscribe(() => {
      requestCount += 1;
    });

    const liked = Array.from(fixtureHost(fixture).querySelectorAll('button')).find(
      (button) => button.getAttribute('aria-label') === 'Liked',
    );
    if (!liked) throw new Error('Liked button not found');
    liked.click();
    expect(feedback).toEqual(['liked']);
    expect(requestCount).toBe(0);
  });

  it('exposes aria-pressed on the active feedback option', () => {
    setItem({ tmdbId: 1, title: 'Liked title', feedback: 'liked' });
    fixture.componentRef.setInput('showFeedback', true);
    fixture.detectChanges();
    const liked = Array.from(fixtureHost(fixture).querySelectorAll('button')).find(
      (button) => button.getAttribute('aria-label') === 'Liked',
    );
    if (!liked) throw new Error('Liked button not found');
    expect(liked.getAttribute('aria-pressed')).toBe('true');

    const watched = Array.from(fixtureHost(fixture).querySelectorAll('button')).find(
      (button) => button.getAttribute('aria-label') === 'Watched',
    );
    if (!watched) throw new Error('Watched button not found');
    expect(watched.getAttribute('aria-pressed')).toBe('true');

    const disliked = Array.from(fixtureHost(fixture).querySelectorAll('button')).find(
      (button) => button.getAttribute('aria-label') === 'Disliked',
    );
    if (!disliked) throw new Error('Disliked button not found');
    expect(disliked.getAttribute('aria-pressed')).toBe('false');
  });

  it('shows rating only in poster meta, not as a separate badge', () => {
    setItem({ tmdbId: 1, title: 'Rated', rating: 8.33 });
    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('8.3★');
    expect(root.querySelectorAll('.mm-media-card__rating')).toHaveLength(0);
  });

  it('uses lazy-loaded poster images with decorative alt text', () => {
    setItem({ tmdbId: 1, title: 'Poster', posterUrl: 'https://example.com/poster.jpg' });
    const image = fixtureHost(fixture).querySelector('img.mm-media-card__image') as HTMLImageElement;
    expect(image).toBeTruthy();
    expect(image.getAttribute('loading')).toBe('lazy');
    expect(image.getAttribute('decoding')).toBe('async');
    expect(image.getAttribute('alt')).toBe('');
  });

  it('falls back when the poster image fails without removing title meta', () => {
    setItem({ tmdbId: 1, title: 'Broken poster', posterUrl: 'https://example.com/bad.jpg' });
    const image = fixtureHost(fixture).querySelector('img.mm-media-card__image') as HTMLImageElement;
    image.dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('img.mm-media-card__image')).toBeNull();
    expect(fixtureHost(fixture).textContent).toContain('Broken poster');
  });

  it('does not reserve an empty badge row when there is no status', () => {
    setItem({ tmdbId: 1, title: 'Clean' });
    expect(fixtureHost(fixture).querySelector('.discover-card__badges')).toBeNull();
  });

  it('keeps the request action for short, long, and absent summaries', () => {
    setItem({ tmdbId: 1, title: 'Short', reason: 'Brief' });
    expect(fixtureHost(fixture).querySelector('.discover-card__footer')).toBeTruthy();

    setItem({
      tmdbId: 1,
      title: 'Long',
      reason: 'One two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen',
    });
    expect(fixtureHost(fixture).querySelector('.discover-card__summary-text')).toBeTruthy();
    expect(fixtureHost(fixture).querySelector('.discover-card__footer')).toBeTruthy();

    setItem({ tmdbId: 1, title: 'No summary' });
    expect(fixtureHost(fixture).querySelector('.discover-card__summary')).toBeNull();
    expect(fixtureHost(fixture).querySelector('.discover-card__footer')).toBeTruthy();
  });

  it('keeps Request in a persistent footer outside the feedback overlay for every source', () => {
    for (const source of [
      { title: 'AI Picks', showFeedback: true },
      { title: 'Jellyseerr', showFeedback: false },
      { title: 'Trakt', showFeedback: false },
    ]) {
      setItem({ tmdbId: 1, title: source.title });
      const showFeedback = source.showFeedback;
      fixture.componentRef.setInput('showFeedback', showFeedback);
      fixture.detectChanges();

      const root = fixtureHost(fixture);
      const footer = root.querySelector('.discover-card__footer');
      const overlay = root.querySelector('mm-poster-action-overlay');
      const request = root.querySelector('.discover-card__footer mm-button button');

      expect(footer).toBeTruthy();
      expect(request).toBeTruthy();
      expect(request?.textContent).toContain('Request');
      expect(overlay).toBeTruthy();
      const liked = overlay?.querySelector('button[aria-label="Liked"]');
      if (showFeedback) {
        expect(liked).toBeTruthy();
      } else {
        expect(liked).toBeNull();
      }
      expect(overlay ? overlay.contains(request) : false).toBe(false);
    }
  });

  it('hides the summary when showSummary is false', () => {
    setItem({ tmdbId: 1, title: 'History item', reason: 'Sharp crime drama; strong overlap.' });
    fixture.componentRef.setInput('showSummary', false);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('.discover-card__summary')).toBeNull();
  });

  function setItem(overrides: Partial<DiscoverCardItem>): void {
    const item: DiscoverCardItem = {
      id: 'card-1',
      title: 'Title',
      type: 'movie',
      tmdbId: 1,
      feedback: null,
      requestState: null,
      inLibrary: false,
      mediaStatus: 'missing',
      service: null,
      serviceHref: null,
      ...overrides,
    };
    fixture.componentRef.setInput('item', item);
    fixture.componentRef.setInput('syncFailed', false);
    fixture.detectChanges();
  }

  function requestButton(): HTMLButtonElement {
    const button = Array.from(fixtureHost(fixture).querySelectorAll('button')).find((candidate) =>
      /Request|Requested|Processing|Open in|Status unavailable|No TMDB/i.test(candidate.textContent),
    );
    if (!button) throw new Error('Request button not found');
    return button;
  }

  function requestWrapper(): HTMLElement {
    return requestButton().closest('[title]') as HTMLElement;
  }
});
