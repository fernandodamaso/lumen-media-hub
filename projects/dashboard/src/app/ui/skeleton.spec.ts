import { TestBed } from '@angular/core/testing';

import { MmSkeleton } from './skeleton';

describe('MmSkeleton', () => {
  it('sweeps a shimmer gradient instead of pulsing', () => {
    const fixture = TestBed.createComponent(MmSkeleton);
    fixture.detectChanges();

    const css = Array.from(document.head.querySelectorAll('style'))
      .map((style) => style.textContent)
      .join('\n');

    expect(css).toContain('mm-skeleton-shimmer');
    expect(css).toContain('linear-gradient');
    expect(css).not.toContain('mm-skeleton-pulse');
    // muted-bg ≈ raised-bg (~6 RGB) makes a stop-based sweep invisible; use a light overlay band.
    expect(css).toContain('--mm-component-text-primary');
    expect(css).toContain('color-mix');
    expect(css).toContain('::after');
    expect(css).toContain('18%');
  });

  it('still renders the configured variant class', () => {
    const fixture = TestBed.createComponent(MmSkeleton);
    fixture.componentRef.setInput('variant', 'rect');
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.mm-skeleton')?.classList.contains('mm-skeleton--rect')).toBe(true);
  });
});
