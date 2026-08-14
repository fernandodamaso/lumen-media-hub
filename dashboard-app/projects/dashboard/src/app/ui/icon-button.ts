import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { LucideLoaderCircle } from '@lucide/angular';

export type MmIconButtonSurface = 'default' | 'overlay';

@Component({
  selector: 'mm-icon-button',
  imports: [NgTemplateOutlet, LucideLoaderCircle],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '[class.mm-icon-button-host--disabled]': 'disabled() || busy()',
  },
  template: `
    @if (href(); as destination) {
      <a
        [class]="controlClass()"
        [href]="destination"
        target="_blank"
        rel="noreferrer"
        [attr.aria-label]="label()"
        [attr.aria-disabled]="disabled() || busy() ? 'true' : null"
        [attr.tabindex]="disabled() || busy() ? -1 : null"
        [attr.aria-busy]="busy() || null"
        [attr.title]="label()"
        (click)="onAnchorClick($event)"
      >
        <ng-container *ngTemplateOutlet="inner" />
      </a>
    } @else {
      <button
        type="button"
        [class]="controlClass()"
        [disabled]="disabled() || busy()"
        [attr.aria-label]="label()"
        [attr.aria-pressed]="toggle() ? pressed() : null"
        [attr.aria-expanded]="expanded() ?? null"
        [attr.aria-controls]="ariaControls() ?? null"
        [attr.aria-busy]="busy() || null"
        [attr.title]="label()"
      >
        <ng-container *ngTemplateOutlet="inner" />
      </button>
    }
    <ng-template #inner>
      @if (busy()) {
        <svg class="mm-icon-button__spinner" lucideLoaderCircle [size]="14" [strokeWidth]="2.2" aria-hidden="true"></svg>
      } @else {
        <ng-content />
      }
    </ng-template>
  `,
  styleUrl: './icon-button.scss',
})
export class MmIconButton {
  readonly label = input.required<string>();
  readonly disabled = input(false);
  readonly busy = input(false);
  readonly pressed = input(false);
  readonly expanded = input<boolean | undefined>();
  readonly ariaControls = input<string | undefined>();
  /** When true, exposes `aria-pressed` as true/false for toggle buttons. */
  readonly toggle = input(false);
  readonly size = input<'sm' | 'md'>('md');
  readonly shape = input<'rounded' | 'circle'>('rounded');
  readonly tone = input<'default' | 'danger'>('default');
  readonly surface = input<MmIconButtonSurface>('default');
  readonly href = input<string | null>(null);

  readonly controlClass = computed(() => {
    const classes = ['mm-icon-button'];
    classes.push(this.size() === 'sm' ? 'mm-icon-button--sm' : 'mm-icon-button--md');
    classes.push(this.shape() === 'circle' ? 'mm-icon-button--circle' : 'mm-icon-button--rounded');
    if (this.pressed()) classes.push('mm-icon-button--pressed');
    if (this.tone() === 'danger') classes.push('mm-icon-button--danger');
    if (this.surface() === 'overlay') classes.push('mm-icon-button--overlay');
    return classes.join(' ');
  });

  onAnchorClick(event: MouseEvent): void {
    if (this.disabled() || this.busy()) event.preventDefault();
  }
}
