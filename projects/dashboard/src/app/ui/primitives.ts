import { AfterViewChecked, ChangeDetectionStrategy, Component, ElementRef, inject, input } from '@angular/core';
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
  standalone: true,
  imports: [LucideLoaderCircle],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button
    [type]="type()"
    [disabled]="disabled() || busy()"
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
  readonly disabled = input(false);
  readonly busy = input(false);
  readonly type = input<'button' | 'submit'>('button');
}

@Component({
  selector: 'mm-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<section class="mm-card" [attr.aria-labelledby]="labelledBy() || null">
    <header class="mm-card__header">
      <div class="mm-card__heading"><ng-content select="[mm-card-header]" /></div>
      <div class="mm-card__actions"><ng-content select="[mm-card-header-actions]" /></div>
    </header>
    <div class="mm-card__body"><ng-content /></div>
    <footer class="mm-card__footer">
      <div class="mm-card__footer-content"><ng-content select="[mm-card-footer]" /></div>
      <div class="mm-card__actions"><ng-content select="[mm-card-footer-actions]" /></div>
    </footer>
  </section>`,
  styles: `
    :host { container-type: inline-size; display: block; height: 100%; }
    .mm-card { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; min-height: 100%; overflow: hidden; border: 1px solid var(--mm-component-border); border-radius: var(--mm-radius-lg); background: var(--mm-component-surface); box-shadow: var(--mm-shadow-card); transition: transform var(--mm-transition-fast), box-shadow var(--mm-transition-fast); }
    @media (hover: hover) and (pointer: fine) {
      .mm-card:hover { transform: translateY(-1px); box-shadow: var(--mm-shadow-card-hover); }
    }
    .mm-card__header, .mm-card__footer { display: flex; align-items: center; justify-content: space-between; gap: var(--mm-space-md); padding: 16px 20px; }
    .mm-card__header { border-bottom: 1px solid var(--mm-component-border); }
    .mm-card__footer { border-top: 1px solid var(--mm-component-border); }
    .mm-card__heading { min-width: 0; }
    .mm-card__actions { display: flex; align-items: center; gap: var(--mm-space-sm); }
    .mm-card__body { min-width: 0; padding: 20px; }
    .mm-card__heading:empty, .mm-card__actions:empty, .mm-card__footer > div:empty { display: none; }
    .mm-card__header:not(:has(.mm-card__heading > *)):not(:has(.mm-card__actions > *)),
    .mm-card__header[hidden], .mm-card__footer[hidden] { display: none; }
    @container (max-width: 520px) {
      .mm-card__header { align-items: stretch; flex-direction: column; }
      .mm-card__actions { justify-content: flex-start; }
    }
  `,
})
export class MmCard implements AfterViewChecked {
  readonly labelledBy = input('');
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  ngAfterViewChecked(): void {
    this.setRegionVisibility('.mm-card__header');
    this.setRegionVisibility('.mm-card__footer');
  }

  private setRegionVisibility(regionSelector: string): void {
    const region = this.host.nativeElement.querySelector<HTMLElement>(regionSelector);
    if (!region) return;
    const isEmpty = !region.querySelector(':scope > div > *');
    region.toggleAttribute('hidden', isEmpty);
    region.style.display = isEmpty ? 'none' : '';
  }
}

@Component({
  selector: 'mm-status',
  standalone: true,
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
      gap: 5px;
      border-radius: 999px;
      padding: 4px 8px;
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
  standalone: true,
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
      font-variant-numeric: tabular-nums;
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
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<article class="mm-poster">
    <div class="mm-poster__art" [style.background]="art()">
      <div class="mm-poster__overlay">
        <div class="mm-poster__head">
          <strong>{{ title() }}</strong>
          @if (rating() !== null) { <span class="mm-poster__rating" aria-label="Rating {{ rating() }} out of 10">★ {{ rating() }}</span> }
        </div>
        <small>{{ meta() }}</small>
      </div>
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
    .mm-poster__art::before {
      content: '';
      position: absolute;
      inset: 0;
      background:
        radial-gradient(circle at 20% 30%, rgb(255 255 255 / 0.06) 0px, rgb(255 255 255 / 0.06) 1px, transparent 1px),
        radial-gradient(circle at 70% 60%, rgb(255 255 255 / 0.05) 0px, rgb(255 255 255 / 0.05) 2px, transparent 2px),
        radial-gradient(circle at 40% 80%, rgb(255 255 255 / 0.04) 0px, rgb(255 255 255 / 0.04) 1px, transparent 1px);
      pointer-events: none;
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
      display: grid;
      gap: 6px;
      width: 100%;
    }
    .mm-poster__head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 8px;
    }
    .mm-poster__head strong { font-size: var(--mm-text-md); line-height: 1.2; }
    .mm-poster__overlay small { color: rgb(255 255 255 / 60%); font-size: var(--mm-text-xs); font-weight: 500; }
    .mm-poster__rating { flex: none; color: #f2cc60; font-size: var(--mm-text-xs); font-variant-numeric: tabular-nums; font-weight: 800; }
  `,
})
export class MmPoster {
  readonly title = input('Moonrise');
  readonly meta = input('2026 · Drama');
  readonly rating = input<number | null>(null);
  readonly art = input('linear-gradient(145deg, color-mix(in srgb, var(--mm-component-accent) 28%, var(--mm-component-card-bg)), var(--mm-component-card-bg) 72%)');
}

export type MmStateCardKind = 'loading' | 'empty' | 'error';

@Component({
  selector: 'mm-state-card',
  standalone: true,
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
      padding: 18px;
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

export type MmSkeletonVariant = 'text' | 'rect' | 'circle';

@Component({
  selector: 'mm-skeleton',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span
    class="mm-skeleton"
    [class.mm-skeleton--text]="variant() === 'text'"
    [class.mm-skeleton--rect]="variant() === 'rect'"
    [class.mm-skeleton--circle]="variant() === 'circle'"
    [style.width]="width()"
    [style.height]="height()"
    aria-hidden="true"
  ></span>`,
  styles: `
    :host { display: inline-block; }
    .mm-skeleton {
      display: inline-block;
      background: var(--mm-component-muted-bg);
      border-radius: var(--mm-radius-sm);
    }
    .mm-skeleton--text {
      width: 100%;
      height: 1em;
      border-radius: calc(1em / 2);
    }
    .mm-skeleton--circle {
      border-radius: 50%;
      aspect-ratio: 1 / 1;
    }
    .mm-skeleton--rect {
      width: 100%;
      height: 100%;
    }
    @media (prefers-reduced-motion: no-preference) {
      .mm-skeleton {
        animation: mm-skeleton-pulse 2s ease-in-out infinite;
      }
    }
    @keyframes mm-skeleton-pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.45; }
    }
  `,
})
export class MmSkeleton {
  readonly variant = input<MmSkeletonVariant>('text');
  readonly width = input<string | undefined>(undefined);
  readonly height = input<string | undefined>(undefined);
}
