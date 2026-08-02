import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../../testing/fixture-host';
import { LandscapeMediaCard } from './landscape-media-card';

describe('LandscapeMediaCard', () => {
  it('preserves the accessible link, play cue, art, and progress semantics', () => {
    const fixture = TestBed.createComponent(LandscapeMediaCard);
    fixture.componentRef.setInput('title', 'Moonrise');
    fixture.componentRef.setInput('ariaLabel', 'Continue Moonrise');
    fixture.componentRef.setInput('art', 'linear-gradient(#000, #111)');
    fixture.componentRef.setInput('href', 'https://jellyfin.example/item');
    fixture.componentRef.setInput('showPlayCue', true);
    fixture.componentRef.setInput('progressPercent', 42);
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    expect(root.querySelector('a')?.getAttribute('aria-label')).toBe('Continue Moonrise');
    expect(root.querySelector('.cw-play')).toBeTruthy();
    expect(root.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('42');
  });
});
