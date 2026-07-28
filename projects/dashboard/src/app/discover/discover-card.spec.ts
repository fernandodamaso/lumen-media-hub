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

  it('disables Request with contract explanations for unavailable states', () => {
    setItem({ tmdbId: 0, title: 'Untitled' });
    expect(requestButton().textContent).toContain('No TMDB ID');
    expect(requestButton().disabled).toBe(true);
    expect(requestWrapper().title).toContain('missing TMDB id');

    setItem({ tmdbId: 1, inLibrary: true, title: 'Owned' });
    expect(requestButton().textContent).toContain('In library');
    expect(requestWrapper().title).toContain('Jellyfin library');

    setItem({ tmdbId: 1, requestState: 'requested', title: 'Queued' });
    expect(requestButton().textContent).toContain('Requested');

    setItem({ tmdbId: 1, title: 'Partial' });
    fixture.componentRef.setInput('syncFailed', true);
    fixture.detectChanges();
    expect(requestButton().textContent).toContain('Added (sync failed)');
    expect(requestWrapper().title).toContain('synchronization failed');
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
    expect(root.querySelectorAll('.mm-poster__rating')).toHaveLength(0);
  });

  it('uses lazy-loaded poster images with decorative alt text', () => {
    setItem({ tmdbId: 1, title: 'Poster', posterUrl: 'https://example.com/poster.jpg' });
    const image = fixtureHost(fixture).querySelector('img.mm-poster__image') as HTMLImageElement;
    expect(image).toBeTruthy();
    expect(image.getAttribute('loading')).toBe('lazy');
    expect(image.getAttribute('decoding')).toBe('async');
    expect(image.getAttribute('alt')).toBe('');
  });

  it('falls back when the poster image fails without removing title meta', () => {
    setItem({ tmdbId: 1, title: 'Broken poster', posterUrl: 'https://example.com/bad.jpg' });
    const image = fixtureHost(fixture).querySelector('img.mm-poster__image') as HTMLImageElement;
    image.dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('img.mm-poster__image')).toBeNull();
    expect(fixtureHost(fixture).textContent).toContain('Broken poster');
  });

  it('does not reserve an empty badge row when there is no status', () => {
    setItem({ tmdbId: 1, title: 'Clean' });
    expect(fixtureHost(fixture).querySelector('.discover-card__badges')).toBeNull();
  });

  it('keeps the footer for short, long, and absent summaries', () => {
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
      ...overrides,
    };
    fixture.componentRef.setInput('item', item);
    fixture.componentRef.setInput('syncFailed', false);
    fixture.detectChanges();
  }

  function requestButton(): HTMLButtonElement {
    const button = Array.from(fixtureHost(fixture).querySelectorAll('button')).find((candidate) =>
      /Request|Requested|In library|No TMDB|sync failed/i.test(candidate.textContent),
    );
    if (!button) throw new Error('Request button not found');
    return button;
  }

  function requestWrapper(): HTMLElement {
    return requestButton().closest('[title]') as HTMLElement;
  }
});
