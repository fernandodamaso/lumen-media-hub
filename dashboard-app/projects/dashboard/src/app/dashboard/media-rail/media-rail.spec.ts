import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { fixtureHost } from '../../../testing/fixture-host';
import { MediaRail } from './media-rail';

@Component({
  imports: [MediaRail],
  template: `
    <mm-media-rail title="Continue Watching" count="4 in progress" linkTo="/library" linkLabel="View all">
      <div class="demo-card">Card A</div>
      <div class="demo-card">Card B</div>
    </mm-media-rail>
  `,
})
class RailHost {}

describe('MediaRail', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [RailHost], providers: [provideRouter([])] });
  });

  it('renders heading, count, link, and projected cards', () => {
    const fixture = TestBed.createComponent(RailHost);
    fixture.detectChanges();
    const root = fixtureHost(fixture);

    expect(root.querySelector('.rail-head h2')?.textContent).toContain('Continue Watching');
    expect(root.querySelector('.rail-head .count')?.textContent).toContain('4 in progress');
    expect(root.querySelector('.rail-head .link')?.getAttribute('href')).toBe('/library');
    expect(root.querySelector('.rail-head .link')?.textContent).toContain('View all');
    expect(root.querySelectorAll('.rail .demo-card')).toHaveLength(2);
  });

  it('scrolls the rail by ±600px from the arrow controls', () => {
    const fixture = TestBed.createComponent(RailHost);
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    const rail = root.querySelector('.rail') as HTMLElement;
    const scrollBy = vi.fn();
    (rail as unknown as { scrollBy: unknown }).scrollBy = scrollBy;

    const [back, forward] = Array.from(root.querySelectorAll<HTMLButtonElement>('.rail-arrow'));
    forward.click();
    expect(scrollBy).toHaveBeenCalledWith({ left: 600, behavior: 'smooth' });
    back.click();
    expect(scrollBy).toHaveBeenCalledWith({ left: -600, behavior: 'smooth' });
    expect(back.getAttribute('aria-label')).toContain('Continue Watching');
  });
});
