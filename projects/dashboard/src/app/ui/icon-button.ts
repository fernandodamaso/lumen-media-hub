import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { LucideLoaderCircle } from '@lucide/angular';

@Component({
  selector: 'mm-icon-button',
  imports: [LucideLoaderCircle],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button
    type="button"
    class="mm-icon-button"
    [disabled]="disabled() || busy()"
    [attr.aria-label]="label()"
    [attr.aria-busy]="busy() || null"
    [attr.title]="label()"
  >
    @if (busy()) {
      <svg class="mm-icon-button__spinner" lucideLoaderCircle [size]="14" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else {
      <ng-content />
    }
  </button>`,
  styles: `
    :host {
      display: inline-flex;
    }
    .mm-icon-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-sm);
      padding: 0;
      background: var(--mm-component-control-bg);
      color: var(--mm-component-text-secondary);
      cursor: pointer;
      transition:
        background var(--mm-transition-fast),
        color var(--mm-transition-fast),
        opacity var(--mm-transition-fast);
    }
    .mm-icon-button:hover:not(:disabled) {
      background: var(--mm-component-muted-bg);
      color: var(--mm-component-text-primary);
    }
    .mm-icon-button:focus-visible {
      outline: 3px solid var(--mm-component-focus-ring);
      outline-offset: 2px;
    }
    .mm-icon-button:disabled {
      cursor: not-allowed;
      opacity: 0.65;
    }
    .mm-icon-button[aria-busy='true'] {
      cursor: wait;
    }
    .mm-icon-button__spinner {
      display: block;
    }
    @media (prefers-reduced-motion: no-preference) {
      .mm-icon-button__spinner {
        animation: mm-icon-button-spin 0.8s linear infinite;
      }
    }
    @keyframes mm-icon-button-spin {
      to { transform: rotate(360deg); }
    }
    @media (pointer: coarse) {
      .mm-icon-button {
        width: 44px;
        height: 44px;
      }
    }
  `,
})
export class MmIconButton {
  readonly label = input.required<string>();
  readonly disabled = input(false);
  readonly busy = input(false);
}
