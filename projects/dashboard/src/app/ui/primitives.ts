import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import {
  LucideAlertCircle,
  LucideCircleCheck,
  LucideInbox,
  LucideInfo,
  LucideLoaderCircle,
  LucideTriangleAlert,
} from '@lucide/angular';

@Component({
  selector: 'mm-button',
  imports: [LucideLoaderCircle],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button
    [type]="type()"
    [disabled]="disabled()"
    [attr.aria-busy]="busy() || null"
    [class]="'mm-button mm-button--' + variant()"
  >
    @if (busy()) {
      <svg lucideLoaderCircle [size]="16" [strokeWidth]="2.2" aria-hidden="true"></svg>
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
      gap: var(--mm-space-sm);
      border: 0;
      border-radius: var(--mm-radius-sm);
      padding: 10px 14px;
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
    .mm-button:disabled {
      cursor: wait;
      opacity: 0.65;
    }
  `,
})
export class MmButton {
  readonly label = input('Continue');
  readonly variant = input<'primary' | 'quiet'>('primary');
  readonly disabled = input(false);
  readonly busy = input(false);
  readonly type = input<'button' | 'submit'>('button');
}

@Component({
  selector: 'mm-status',
  imports: [LucideCircleCheck, LucideInfo, LucideAlertCircle, LucideTriangleAlert],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span role="status" [class]="'mm-status mm-status--' + tone()">
    @if (tone() === 'success') {
      <svg lucideCircleCheck [size]="15" aria-hidden="true"></svg>
    } @else if (tone() === 'danger') {
      <svg lucideAlertCircle [size]="15" aria-hidden="true"></svg>
    } @else if (tone() === 'warning') {
      <svg lucideTriangleAlert [size]="15" aria-hidden="true"></svg>
    } @else {
      <svg lucideInfo [size]="15" aria-hidden="true"></svg>
    }
    <span><ng-content /></span>
  </span>`,
  styles: `
    .mm-status {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border-radius: 999px;
      padding: 6px 10px;
      background: var(--mm-component-muted-bg);
      color: var(--mm-component-text-secondary);
      font: 700 var(--mm-text-xs)/1 var(--mm-font-body);
    }
    .mm-status--success {
      color: var(--mm-component-success);
    }
    .mm-status--warning {
      color: var(--mm-component-warning);
    }
    .mm-status--danger {
      color: var(--mm-component-danger);
    }
    .mm-status--info {
      color: var(--mm-component-accent);
    }
  `,
})
export class MmStatus {
  readonly tone = input<'success' | 'warning' | 'danger' | 'info'>('info');
}

@Component({
  selector: 'mm-progress',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div
      class="mm-progress"
      role="progressbar"
      [attr.aria-label]="label()"
      [attr.aria-valuenow]="value()"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <div class="mm-progress__bar" [style.width.%]="value()"></div>
    </div>
    <span class="mm-progress__label">{{ value() }}%</span>`,
  styles: `
    :host {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
    }
    .mm-progress {
      height: 8px;
      overflow: hidden;
      flex: 1;
      border-radius: 999px;
      background: var(--mm-component-border);
    }
    .mm-progress__bar {
      height: 100%;
      border-radius: inherit;
      background: var(--mm-component-accent);
      transition: width var(--mm-transition-normal);
    }
    .mm-progress__label {
      min-width: 38px;
      color: var(--mm-component-text-secondary);
      font-size: var(--mm-text-xs);
      text-align: right;
    }
  `,
})
export class MmProgress {
  readonly value = input(0);
  readonly label = input('Progress');
}

@Component({
  selector: 'mm-poster',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<article class="mm-poster">
    <div class="mm-poster__art" [style.background]="art()">
      <span class="mm-poster__overlay" aria-hidden="true">{{ title() }}</span>
    </div>
    <div class="mm-poster__body">
      <strong>{{ title() }}</strong>
      <small>{{ meta() }}</small>
    </div>
  </article>`,
  styles: `
    :host {
      display: block;
      width: 180px;
      max-width: 100%;
    }
    .mm-poster {
      width: 100%;
      overflow: hidden;
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-md);
      background: var(--mm-component-card-bg);
      box-shadow: var(--mm-shadow-card);
    }
    .mm-poster__art {
      position: relative;
      aspect-ratio: 2 / 3;
      display: flex;
      align-items: end;
      padding: 14px;
      color: #fff;
      font-size: var(--mm-text-lg);
      font-weight: 800;
      letter-spacing: -0.03em;
    }
    .mm-poster__art::after {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(transparent 40%, rgb(0 0 0 / 72%));
      pointer-events: none;
    }
    .mm-poster__overlay {
      position: relative;
      z-index: 1;
    }
    .mm-poster__body {
      display: grid;
      gap: 5px;
      padding: 12px;
    }
    .mm-poster__body strong {
      color: var(--mm-component-text-primary);
      font-size: var(--mm-text-sm);
    }
    .mm-poster__body small {
      color: var(--mm-component-text-muted);
    }
  `,
})
export class MmPoster {
  readonly title = input('Moonrise');
  readonly meta = input('2026 ┬╖ Drama');
  readonly art = input('linear-gradient(145deg, var(--mm-component-accent), var(--mm-component-card-bg) 65%)');
}

export type MmStateCardKind = 'loading' | 'empty' | 'error';

@Component({
  selector: 'mm-state-card',
  imports: [LucideLoaderCircle, LucideInbox, LucideAlertCircle],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<section [class]="'mm-state-card mm-state-card--' + tone()">
    <div class="mm-state-card__icon" aria-hidden="true">
      @if (kind() === 'loading') {
        <svg lucideLoaderCircle [size]="18" [strokeWidth]="2.2"></svg>
      } @else if (kind() === 'error') {
        <svg lucideAlertCircle [size]="18" [strokeWidth]="2.2"></svg>
      } @else {
        <svg lucideInbox [size]="18" [strokeWidth]="2.2"></svg>
      }
    </div>
    <h3>{{ title() }}</h3>
    <p>{{ message() }}</p>
    <ng-content />
  </section>`,
  styles: `
    .mm-state-card {
      display: grid;
      justify-items: start;
      gap: var(--mm-space-sm);
      padding: 22px;
      border: 1px dashed var(--mm-component-border);
      border-radius: var(--mm-radius-md);
      background: var(--mm-component-card-bg);
    }
    .mm-state-card__icon {
      display: grid;
      place-items: center;
      width: 34px;
      height: 34px;
      border-radius: 50%;
      background: var(--mm-component-muted-bg);
      color: var(--mm-component-accent);
    }
    .mm-state-card--danger .mm-state-card__icon {
      color: var(--mm-component-danger);
    }
    h3,
    p {
      margin: 0;
    }
    h3 {
      color: var(--mm-component-text-primary);
      font-size: var(--mm-text-md);
    }
    p {
      color: var(--mm-component-text-secondary);
      font-size: var(--mm-text-sm);
      line-height: 1.5;
    }
  `,
})
export class MmStateCard {
  readonly kind = input<MmStateCardKind>('empty');
  readonly title = input('Nothing here yet');
  readonly message = input('There is no content to show right now.');
  readonly tone = input<'default' | 'danger'>('default');
}
