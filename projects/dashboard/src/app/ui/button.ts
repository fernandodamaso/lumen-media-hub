import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { LucideLoaderCircle, LucidePause, LucidePlay } from '@lucide/angular';

@Component({
  selector: 'mm-button',
  imports: [LucideLoaderCircle, LucidePause, LucidePlay],
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
      min-height: 34px;
      gap: var(--mm-space-sm);
      border: 0;
      border-radius: var(--mm-radius-sm);
      padding: 8px 12px;
      background: var(--mm-component-accent);
      color: var(--mm-component-on-accent);
      cursor: pointer;
      font: 700 var(--mm-text-sm)/1 var(--mm-font-body);
      transition:
        background var(--mm-transition-fast),
        color var(--mm-transition-fast),
        opacity var(--mm-transition-fast),
        transform var(--mm-transition-fast);
    }
    .mm-button:hover:not(:disabled) {
      background: var(--mm-semantic-accent-strong);
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
    }
    .mm-button--quiet:hover:not(:disabled) {
      background: var(--mm-component-muted-bg);
    }
    .mm-button--success {
      background: var(--mm-component-success);
      color: var(--mm-component-on-accent);
    }
    .mm-button--warning {
      background: var(--mm-component-warning);
      color: var(--mm-semantic-text-inverse);
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
  readonly icon = input<'pause' | 'play' | ''>('');
  readonly disabled = input(false);
  readonly busy = input(false);
  readonly type = input<'button' | 'submit'>('button');
}
