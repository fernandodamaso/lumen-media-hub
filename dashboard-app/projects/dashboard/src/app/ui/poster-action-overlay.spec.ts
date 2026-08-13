import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmIconButton } from './icon-button';
import { MmPosterActionOverlay } from './poster-action-overlay';

@Component({
  standalone: true,
  imports: [MmPosterActionOverlay, MmIconButton],
  template: `
    <mm-poster-action-overlay ariaLabel="Actions for Dune">
      <div data-testid="poster">Poster</div>
      <mm-icon-button label="Play" surface="overlay" />
    </mm-poster-action-overlay>
  `,
})
class PosterActionOverlayHost {}

describe('MmPosterActionOverlay', () => {
  it('projects the poster separately from overlay icon buttons', () => {
    const fixture = TestBed.createComponent(PosterActionOverlayHost);
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    const poster = root.querySelector('.mm-poster-action-overlay__poster [data-testid="poster"]');
    const actions = root.querySelector('.mm-poster-action-overlay__actions');
    expect(poster).toBeTruthy();
    expect(actions?.querySelector('button[aria-label="Play"]')).toBeTruthy();
    expect(poster?.querySelector('button')).toBeNull();
  });
});
