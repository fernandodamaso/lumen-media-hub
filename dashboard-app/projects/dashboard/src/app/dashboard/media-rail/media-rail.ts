import { ChangeDetectionStrategy, Component, ElementRef, input, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LucideChevronLeft, LucideChevronRight } from '@lucide/angular';

/** Generic horizontal content rail: serif heading, optional count/link, arrow scrolling. */
@Component({
  selector: 'mm-media-rail',
  imports: [RouterLink, LucideChevronLeft, LucideChevronRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="rail-head">
      <h2>{{ title() }}</h2>
      @if (count()) {
        <span class="count">{{ count() }}</span>
      }
      @if (linkTo(); as to) {
        <a class="link" [routerLink]="to">{{ linkLabel() }} →</a>
      }
      <div class="rail-nav">
        <button
          type="button"
          class="rail-arrow"
          [attr.aria-label]="'Scroll ' + title() + ' back'"
          (click)="scroll(-1)"
        >
          <svg lucideChevronLeft [size]="13" aria-hidden="true"></svg>
        </button>
        <button
          type="button"
          class="rail-arrow"
          [attr.aria-label]="'Scroll ' + title() + ' forward'"
          (click)="scroll(1)"
        >
          <svg lucideChevronRight [size]="13" aria-hidden="true"></svg>
        </button>
      </div>
    </div>
    <div class="rail" #rail><ng-content /></div>
  `,
  styleUrl: './media-rail.scss',
})
export class MediaRail {
  readonly title = input.required<string>();
  readonly count = input('');
  readonly linkTo = input<string | null>(null);
  readonly linkLabel = input('View all');

  private readonly rail = viewChild.required<ElementRef<HTMLElement>>('rail');

  scroll(direction: 1 | -1): void {
    this.rail().nativeElement.scrollBy({ left: direction * 600, behavior: 'smooth' });
  }
}
