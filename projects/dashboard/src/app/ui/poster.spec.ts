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
});
