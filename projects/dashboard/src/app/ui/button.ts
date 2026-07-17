import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { LucideLoaderCircle, LucidePause, LucidePlay, LucidePlus, LucideSquareArrowOutUpRight } from '@lucide/angular';

@Component({
  selector: 'mm-button',
  imports: [LucideLoaderCircle, LucidePause, LucidePlay, LucidePlus, LucideSquareArrowOutUpRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button
    [type]="type()"
    [disabled]="disabled() || busy()"
    [attr.aria-busy]="busy() || null"
    [class]="'mm-button mm-button--' + variant()"
  >
    @if (busy()) {
      <svg lucideLoaderCircle [size]="16" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'pause') {
      <svg lucidePause [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'play') {
      <svg lucidePlay [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'plus') {
      <svg lucidePlus [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    } @else if (icon() === 'external-link') {
      <svg lucideSquareArrowOutUpRight [size]="15" [strokeWidth]="2.2" aria-hidden="true"></svg>
    }
    {{ label() }}
  </button>`,
  styles: `
    :host {
      display: inline-block;
    }
    .mm-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 40px;
      gap: var(--mm-space-sm);
      border: 0;
      border-radius: var(--mm-radius-sm);
      padding: 8px 14px;
      background: var(--mm-component-accent-strong);
      color: var(--mm-component-on-accent);
      cursor: pointer;
      font: 700 var(--mm-text-md)/1 var(--mm-font-body);
      white-space: nowrap;
      transition:
        background var(--mm-transition-fast),
        color var(--mm-transition-fast),
        opacity var(--mm-transition-fast),
        transform var(--mm-transition-fast);
    }
    .mm-button:hover:not(:disabled) {
      background: color-mix(in srgb, var(--mm-component-accent-strong) 86%, var(--mm-component-on-accent));
    }
    .mm-button:active:not(:disabled) {
      transform: scale(0.98);
    }
    .mm-button:focus-visible {
      outline: 3px solid var(--mm-component-focus-ring);
      outline-offset: 2px;
    }
    .mm-button--quiet {
      background: var(--mm-component-control-bg);
      color: var(--mm-component-text-primary);
      border: 1px solid var(--mm-component-border);
    }
    .mm-button--quiet:hover:not(:disabled) {
      background: var(--mm-component-muted-bg);
    }
    .mm-button--success {
      background: var(--mm-component-success);
      color: var(--mm-component-on-success);
    }
    .mm-button--warning {
      background: var(--mm-component-warning);
      color: var(--mm-component-on-warning);
    }
    .mm-button:disabled {
      cursor: not-allowed;
      opacity: 0.65;
    }
    .mm-button[aria-busy='true'] { cursor: wait; }
    @media (max-width: 900px), (pointer: coarse) {
      .mm-button { min-height: 44px; }
    }
  `,
})
export class MmButton {
  readonly label = input('Continue');
  readonly variant = input<'primary' | 'quiet' | 'success' | 'warning'>('primary');
  readonly icon = input<'pause' | 'play' | 'plus' | 'external-link' | ''>('');
  readonly disabled = input(false);
  readonly busy = input(false);
  readonly type = input<'button' | 'submit'>('button');
}
