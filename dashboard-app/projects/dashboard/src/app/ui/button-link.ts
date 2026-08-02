import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  LucideLoaderCircle,
  LucideInfo,
  LucidePause,
  LucidePlay,
  LucidePlus,
  LucideRefreshCw,
  LucideSquareArrowOutUpRight,
} from '@lucide/angular';

@Component({
  selector: 'mm-button-link',
  imports: [NgTemplateOutlet, RouterLink, LucideInfo, LucideLoaderCircle, LucidePause, LucidePlay, LucidePlus, LucideRefreshCw, LucideSquareArrowOutUpRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `@if (mode() === 'external') {
    <a
      class="mm-button"
      [class]="classes()"
      [href]="destination()"
      target="_blank"
      rel="noreferrer"
      [attr.data-testid]="testId() || null"
      [attr.aria-disabled]="disabled() || busy() ? 'true' : null"
      [attr.tabindex]="disabled() || busy() ? -1 : null"
      (click)="onClick($event)"
    >
      <ng-container *ngTemplateOutlet="content" />
    </a>
  } @else {
    <a
      class="mm-button"
      [class]="classes()"
      [routerLink]="destination()"
      [attr.data-testid]="testId() || null"
      [attr.aria-disabled]="disabled() || busy() ? 'true' : null"
      [attr.tabindex]="disabled() || busy() ? -1 : null"
      (click)="onClick($event)"
    >
      <ng-container *ngTemplateOutlet="content" />
    </a>
  }
  <ng-template #content>
    @if (busy()) {
      <svg class="mm-button__spinner" lucideLoaderCircle [size]="16" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'pause') {
      <svg lucidePause [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'play') {
      <svg lucidePlay [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'plus') {
      <svg lucidePlus [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'refresh') {
      <svg lucideRefreshCw [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'external-link') {
      <svg lucideSquareArrowOutUpRight [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'info') {
      <svg lucideInfo [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    }
    {{ label() }}
  </ng-template>`,
  styleUrl: './button.scss',
})
export class MmButtonLink {
  readonly destination = input.required<string>();
  readonly testId = input('');
  readonly mode = input<'internal' | 'external'>('internal');
  readonly label = input('Continue');
  readonly variant = input<'primary' | 'quiet' | 'success' | 'warning' | 'danger' | 'gold' | 'ghost' | 'chip'>('primary');
  readonly icon = input<'pause' | 'play' | 'plus' | 'refresh' | 'external-link' | 'info' | ''>('');
  readonly disabled = input(false);
  readonly busy = input(false);
  readonly size = input<'sm' | 'md' | 'lg'>('md');
  readonly solid = input(false);
  readonly liftOnHover = input(true);

  classes(): string {
    return `mm-button--${this.variant()} mm-button--${this.size()}${this.solid() ? ' solid' : ''}${this.liftOnHover() ? '' : ' mm-button--flat-hover'}`;
  }

  onClick(event: MouseEvent): void {
    if (this.disabled() || this.busy()) event.preventDefault();
  }
}
