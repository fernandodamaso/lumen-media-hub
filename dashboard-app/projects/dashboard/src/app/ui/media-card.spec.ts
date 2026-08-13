import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmMediaCard } from './media-card';

describe('MmMediaCard', () => {
  it('renders lazy-loaded network images when imageUrl is set', () => {
    const fixture = TestBed.createComponent(MmMediaCard);
    fixture.componentRef.setInput('imageUrl', 'https://example.com/poster.jpg');
    fixture.detectChanges();

    const image = fixtureHost(fixture).querySelector('img.mm-media-card__image') as HTMLImageElement;
    expect(image).toBeTruthy();
    expect(image.getAttribute('loading')).toBe('lazy');
    expect(image.getAttribute('decoding')).toBe('async');
    expect(image.getAttribute('alt')).toBe('');
  });

  it('renders portrait metadata, status tag, and accessible progress', () => {
    const fixture = TestBed.createComponent(MmMediaCard);
    fixture.componentRef.setInput('title', 'Moonrise');
    fixture.componentRef.setInput('episode', 'S1 · E6');
    fixture.componentRef.setInput('tag', 'Continue');
    fixture.componentRef.setInput('progress', 64);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.mm-media-card__episode')?.textContent).toContain('S1 · E6');
    expect(root.querySelector('.mm-media-card__tag')?.textContent).toContain('Continue');
    expect(root.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('64');
  });

  it('renders the landscape layout with subtitle and progress', () => {
    const fixture = TestBed.createComponent(MmMediaCard);
    fixture.componentRef.setInput('layout', 'landscape');
    fixture.componentRef.setInput('title', 'Moonrise');
    fixture.componentRef.setInput('subtitle', 'Season 1');
    fixture.componentRef.setInput('progress', 42);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.classList.contains('mm-media-card--landscape')).toBe(true);
    expect(root.querySelector('.mm-media-card--landscape')).toBeTruthy();
    expect(root.querySelector('.mm-media-card__shade')).toBeTruthy();
    expect(root.querySelector('.mm-media-card__sub')?.textContent).toContain('Season 1');
    expect(root.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('42');
  });

  it('renders landscape long title and subtitle with NEW tag and link semantics', () => {
    const fixture = TestBed.createComponent(MmMediaCard);
    const longTitle =
      'Saga of Tanya the Evil and the Very Long Continuation of the Imperial Mage Corps';
    const longSubtitle =
      'S02E05 · Lamb and the extraordinarily detailed episode title that should clamp to two lines';
    fixture.componentRef.setInput('layout', 'landscape');
    fixture.componentRef.setInput('title', longTitle);
    fixture.componentRef.setInput('subtitle', longSubtitle);
    fixture.componentRef.setInput('tag', 'NEW');
    fixture.componentRef.setInput('tagTone', 'success');
    fixture.componentRef.setInput('href', 'http://jf.local/web/index.html#!/details?id=ep-1');
    fixture.componentRef.setInput('linkLabel', 'Open Saga of Tanya the Evil, S02E05, Lamb in Jellyfin');
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    const name = root.querySelector('.mm-media-card__name') as HTMLElement;
    const sub = root.querySelector('.mm-media-card__sub') as HTMLElement;
    const link = root.querySelector('.mm-media-card__hit') as HTMLAnchorElement;
    const tag = root.querySelector('.mm-media-card__tag');

    expect(root.classList.contains('mm-media-card--landscape')).toBe(true);
    expect(name.textContent).toContain(longTitle);
    expect(sub.textContent).toContain(longSubtitle);
    expect(getComputedStyle(name).textOverflow).toBe('ellipsis');
    expect(getComputedStyle(name).whiteSpace).toBe('nowrap');
    expect(getComputedStyle(sub).webkitLineClamp).toBe('2');
    expect(tag?.textContent).toContain('NEW');
    expect(tag?.classList.contains('mm-media-card__tag--success')).toBe(true);
    expect(link.getAttribute('href')).toContain('details?id=ep-1');
    expect(link.getAttribute('aria-label')).toBe(
      'Open Saga of Tanya the Evil, S02E05, Lamb in Jellyfin',
    );
    expect(root.querySelector('[role="progressbar"]')).toBeNull();
    expect(root.querySelector('.mm-media-card__play-cue')).toBeNull();
  });

  it('renders a full-card external link with the default label', () => {
    const fixture = TestBed.createComponent(MmMediaCard);
    fixture.componentRef.setInput('title', 'Dune');
    fixture.componentRef.setInput('href', 'https://trakt.tv/movies/dune-2021');
    fixture.detectChanges();

    const link = fixtureHost(fixture).querySelector('.mm-media-card__hit') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('https://trakt.tv/movies/dune-2021');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noreferrer');
    expect(link.getAttribute('aria-label')).toBe('Open Dune');
  });

  it('shows the play cue only when enabled and linked', () => {
    const fixture = TestBed.createComponent(MmMediaCard);
    fixture.componentRef.setInput('showPlayCue', true);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('.mm-media-card__play-cue')).toBeNull();

    fixture.componentRef.setInput('href', 'https://jellyfin.example/item');
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('.mm-media-card__play-cue')).toBeTruthy();
  });

  it('renders below captions and hides the overlay', () => {
    const fixture = TestBed.createComponent(MmMediaCard);
    fixture.componentRef.setInput('title', 'Moonrise');
    fixture.componentRef.setInput('subtitle', '2024 - Movie');
    fixture.componentRef.setInput('captionPlacement', 'below');
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.mm-media-card--caption-below')).toBeTruthy();
    expect(root.querySelector('.mm-media-card__caption')?.textContent).toContain('Moonrise');
    expect(root.querySelector('.mm-media-card__overlay')).toBeNull();
  });

  it('renders neither caption when placement is none', () => {
    const fixture = TestBed.createComponent(MmMediaCard);
    fixture.componentRef.setInput('captionPlacement', 'none');
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.mm-media-card__overlay')).toBeNull();
    expect(root.querySelector('.mm-media-card__caption')).toBeNull();
  });

  it('retries network artwork when retryToken changes after an image error', () => {
    const fixture = TestBed.createComponent(MmMediaCard);
    fixture.componentRef.setInput('imageUrl', 'https://example.com/poster.jpg');
    fixture.detectChanges();

    const image = fixtureHost(fixture).querySelector('img.mm-media-card__image') as HTMLImageElement;
    image.dispatchEvent(new Event('error'));
    fixture.detectChanges();

    expect(fixtureHost(fixture).querySelector('img.mm-media-card__image')).toBeNull();

    fixture.componentRef.setInput('retryToken', 1);
    fixture.detectChanges();

    const retried = fixtureHost(fixture).querySelector('img.mm-media-card__image') as HTMLImageElement;
    expect(retried).toBeTruthy();
    expect(retried.getAttribute('src')).toBe('https://example.com/poster.jpg');
  });

  it('rounds the rating to at most one decimal', () => {
    const fixture = TestBed.createComponent(MmMediaCard);
    fixture.componentRef.setInput('title', 'Moonrise');
    fixture.componentRef.setInput('rating', 7.849999);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.mm-media-card__rating')?.textContent).toContain('7.8');
    expect(root.querySelector('.mm-media-card__rating')?.getAttribute('aria-label')).toContain('7.8');
  });

  it('keeps the play cue by default when linked and showPlayCue is enabled', () => {
    const fixture = TestBed.createComponent(MmMediaCard);
    fixture.componentRef.setInput('title', 'Dune');
    fixture.componentRef.setInput('href', 'https://jf.example/dune');
    fixture.componentRef.setInput('showPlayCue', true);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.mm-media-card__play-cue')).toBeTruthy();
  });
});
