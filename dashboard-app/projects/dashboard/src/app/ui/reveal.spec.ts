import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { MmReveal } from './reveal';

@Component({
  imports: [MmReveal],
  template: `<section mmReveal data-testid="target">Hello</section>`,
})
class RevealHost {}

class FakeIntersectionObserver {
  private static readonly _instances: FakeIntersectionObserver[] = [];
  static get instances(): readonly FakeIntersectionObserver[] {
    return FakeIntersectionObserver._instances;
  }
  static reset(): void {
    FakeIntersectionObserver._instances.length = 0;
  }
  disconnected = false;
  private readonly observed: Element[] = [];
  constructor(
    private readonly callback: IntersectionObserverCallback,
    readonly options?: IntersectionObserverInit,
  ) {
    FakeIntersectionObserver._instances.push(this);
  }
  observe(el: Element): void {
    this.observed.push(el);
  }
  unobserve(): void {}
  disconnect(): void {
    this.disconnected = true;
  }
  trigger(isIntersecting: boolean): void {
    this.callback(
      [{ isIntersecting, target: this.observed[0] } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    );
  }
}

describe('MmReveal', () => {
  let originalObserver: typeof IntersectionObserver | undefined;
  let matchMediaSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    FakeIntersectionObserver.reset();
    originalObserver = (window as { IntersectionObserver?: typeof IntersectionObserver }).IntersectionObserver;
    (window as unknown as { IntersectionObserver: unknown }).IntersectionObserver = FakeIntersectionObserver;
    matchMediaSpy = vi.fn(() => ({ matches: false }) as MediaQueryList);
    (window as unknown as { matchMedia: unknown }).matchMedia = matchMediaSpy;
    TestBed.configureTestingModule({ imports: [RevealHost] });
  });

  afterEach(() => {
    (window as unknown as { IntersectionObserver: unknown }).IntersectionObserver = originalObserver;
  });

  it('starts hidden and reveals when the element intersects', () => {
    const fixture = TestBed.createComponent(RevealHost);
    fixture.detectChanges();
    const target = fixtureHost(fixture).querySelector('[data-testid="target"]');
    expect(target).toBeTruthy();
    if (!target) return;

    expect(target.classList.contains('mm-reveal')).toBe(true);
    expect(target.classList.contains('mm-reveal--in')).toBe(false);
    expect(FakeIntersectionObserver.instances).toHaveLength(1);
    expect(FakeIntersectionObserver.instances[0].options?.threshold).toBeCloseTo(0.1);

    FakeIntersectionObserver.instances[0].trigger(true);
    fixture.detectChanges();
    expect(target.classList.contains('mm-reveal--in')).toBe(true);
    expect(FakeIntersectionObserver.instances[0].disconnected).toBe(true);
  });

  it('stays hidden while the element is not intersecting', () => {
    const fixture = TestBed.createComponent(RevealHost);
    fixture.detectChanges();
    FakeIntersectionObserver.instances[0].trigger(false);
    fixture.detectChanges();
    const target = fixtureHost(fixture).querySelector('[data-testid="target"]');
    expect(target?.classList.contains('mm-reveal--in')).toBe(false);
  });

  it('reveals immediately under prefers-reduced-motion without observing', () => {
    matchMediaSpy.mockReturnValue({ matches: true });
    const fixture = TestBed.createComponent(RevealHost);
    fixture.detectChanges();
    const target = fixtureHost(fixture).querySelector('[data-testid="target"]');
    expect(target?.classList.contains('mm-reveal--in')).toBe(true);
    expect(FakeIntersectionObserver.instances).toHaveLength(0);
  });
});
