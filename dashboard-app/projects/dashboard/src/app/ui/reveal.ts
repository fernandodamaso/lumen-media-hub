import { AfterViewInit, Directive, ElementRef, OnDestroy, inject, signal } from '@angular/core';

/**
 * Scroll-reveal: fades + rises the host into view once (Lumen `.reveal` semantics).
 * Styles live globally in `ui/media-ui.scss` (`.mm-reveal` / `.mm-reveal--in`).
 * Immediately reveals under `prefers-reduced-motion` or without IntersectionObserver.
 */
@Directive({
  selector: '[mmReveal]',
  host: {
    class: 'mm-reveal',
    '[class.mm-reveal--in]': 'revealed()',
  },
})
export class MmReveal implements AfterViewInit, OnDestroy {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  readonly revealed = signal(false);
  private observer?: IntersectionObserver;

  ngAfterViewInit(): void {
    const media =
      typeof window.matchMedia === 'function'
        ? window.matchMedia('(prefers-reduced-motion: reduce)')
        : null;
    const reduced = media?.matches ?? false;
    if (reduced || typeof IntersectionObserver === 'undefined') {
      this.revealed.set(true);
      return;
    }
    this.observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          this.reveal();
        }
      },
      { threshold: 0.1 },
    );
    this.observer.observe(this.host.nativeElement);

    const rect = this.host.nativeElement.getBoundingClientRect();
    if (rect.bottom > 0 && rect.top < window.innerHeight) this.reveal();
  }

  ngOnDestroy(): void {
    this.observer?.disconnect();
  }

  private reveal(): void {
    this.revealed.set(true);
    this.observer?.disconnect();
  }
}
