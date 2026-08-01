import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmPoster } from './poster';

describe('MmPoster', () => {
  it('renders lazy-loaded network images when imageUrl is set', () => {
    const fixture = TestBed.createComponent(MmPoster);
    fixture.componentRef.setInput('imageUrl', 'https://example.com/poster.jpg');
    fixture.detectChanges();

    const image = fixtureHost(fixture).querySelector('img.mm-poster__image') as HTMLImageElement;
    expect(image).toBeTruthy();
    expect(image.getAttribute('loading')).toBe('lazy');
    expect(image.getAttribute('decoding')).toBe('async');
    expect(image.getAttribute('alt')).toBe('');
  });

  it('renders episode eyebrow, status tag, and progress hairline', () => {
    const fixture = TestBed.createComponent(MmPoster);
    fixture.componentRef.setInput('episode', 'S1 · E6');
    fixture.componentRef.setInput('tag', 'Continue');
    fixture.componentRef.setInput('progress', 64);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.mm-poster__episode')?.textContent).toContain('S1 · E6');
    expect(root.querySelector('.mm-poster__tag')?.textContent).toContain('Continue');
    expect(root.querySelector('.mm-poster__progress-bar')?.getAttribute('style')).toContain('64%');
  });

  it('renders a full-card external link when href is set', () => {
    const fixture = TestBed.createComponent(MmPoster);
    fixture.componentRef.setInput('title', 'Dune');
    fixture.componentRef.setInput('href', 'https://trakt.tv/movies/dune-2021');
    fixture.componentRef.setInput('linkLabel', 'Open Dune on Trakt');
    fixture.detectChanges();

    const link = fixtureHost(fixture).querySelector('.mm-poster__hit') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('https://trakt.tv/movies/dune-2021');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noreferrer');
    expect(link.getAttribute('aria-label')).toBe('Open Dune on Trakt');
  });

  it('keeps posters without href non-clickable', () => {
    const fixture = TestBed.createComponent(MmPoster);
    fixture.detectChanges();

    expect(fixtureHost(fixture).querySelector('a')).toBeNull();
  });

  it('renders below captions and an optional play cue', () => {
    const fixture = TestBed.createComponent(MmPoster);
    fixture.componentRef.setInput('title', 'Moonrise');
    fixture.componentRef.setInput('meta', '2024 - Movie');
    fixture.componentRef.setInput('captionPlacement', 'below');
    fixture.componentRef.setInput('href', 'https://jellyfin.example/item');
    fixture.componentRef.setInput('showPlayCue', true);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.mm-poster--caption-below')).toBeTruthy();
    expect(root.querySelector('.mm-poster__caption')?.textContent).toContain('Moonrise');
    expect(root.querySelector('.mm-poster__play-cue')).toBeTruthy();
    expect(root.querySelector('.mm-poster__overlay')).toBeNull();
  });
});
