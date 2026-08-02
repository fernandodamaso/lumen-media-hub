import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MmButtonIcon } from './button-icon';
import { MmButtonIconName, MmButtonSize, MmButtonVariant, mmButtonClasses } from './button-shared';

@Component({
  selector: 'mm-button-link',
  imports: [NgTemplateOutlet, RouterLink, MmButtonIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `@if (mode() === 'external') {
    <a
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
    <mm-button-icon [icon]="icon()" [busy]="busy()" />
    {{ label() }}
  </ng-template>`,
  styleUrl: './button.scss',
})
export class MmButtonLink {
  readonly destination = input.required<string>();
  readonly testId = input('');
  readonly mode = input<'internal' | 'external'>('internal');
  readonly label = input('Continue');
  readonly variant = input<MmButtonVariant>('primary');
  readonly icon = input<MmButtonIconName>('');
  readonly disabled = input(false);
  readonly busy = input(false);
  readonly size = input<MmButtonSize>('md');
  readonly solid = input(false);
  readonly liftOnHover = input(true);

  classes(): string {
    return mmButtonClasses({
      variant: this.variant(),
      size: this.size(),
      solid: this.solid(),
      liftOnHover: this.liftOnHover(),
    });
  }

  onClick(event: MouseEvent): void {
    if (this.disabled() || this.busy()) event.preventDefault();
  }
}
