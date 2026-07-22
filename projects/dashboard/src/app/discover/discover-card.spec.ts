import { ComponentFixture, TestBed } from '@angular/core/testing';
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

    const liked = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>,
    ).find((button) => button.getAttribute('aria-label') === 'Liked');
    if (!liked) throw new Error('Liked button not found');
    liked.click();
    expect(feedback).toEqual(['liked']);
    expect(requestCount).toBe(0);
  });

  it('exposes aria-pressed on the active feedback option', () => {
    setItem({ tmdbId: 1, title: 'Liked title', feedback: 'liked' });
    fixture.componentRef.setInput('showFeedback', true);
    fixture.detectChanges();
    const liked = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>,
    ).find((button) => button.getAttribute('aria-label') === 'Liked');
    if (!liked) throw new Error('Liked button not found');
    expect(liked.getAttribute('aria-pressed')).toBe('true');
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
    const button = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>,
    ).find((candidate) =>
      /Request|Requested|In library|No TMDB|sync failed/i.test(candidate.textContent),
    );
    if (!button) throw new Error('Request button not found');
    return button;
  }

  function requestWrapper(): HTMLElement {
    return requestButton().closest('[title]') as HTMLElement;
  }
});
