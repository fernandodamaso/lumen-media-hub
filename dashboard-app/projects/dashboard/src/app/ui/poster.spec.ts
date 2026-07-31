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
});
