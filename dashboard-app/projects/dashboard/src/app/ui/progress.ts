import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type MmProgressTone = 'accent' | 'success' | 'warning' | 'info' | 'premiere' | 'violet' | 'muted';

@Component({
  selector: 'mm-progress',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div
      [class]="'mm-progress mm-progress--' + tone()"
      role="progressbar"
      [attr.aria-label]="label()"
      [attr.aria-valuenow]="normalized()"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <div class="mm-progress__bar" [class.mm-progress__bar--live]="live()" [style.width.%]="normalized()"></div>
    </div>
    @if (showLabel()) {
      <span class="mm-progress__label">{{ normalized() }}%</span>
    }`,
  styles: `
    :host {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
    }
    .mm-progress {
      height: var(--mm-progress-height, 5px);
      overflow: hidden;
      flex: 1;
      border-radius: 999px;
      background: var(--mm-component-border);
    }
    .mm-progress__bar {
      height: 100%;
      min-width: var(--mm-progress-min-fill, 0);
      border-radius: inherit;
      position: relative;
      background: linear-gradient(90deg, var(--mm-progress-start, var(--mm-component-accent)), var(--mm-progress-end, var(--mm-component-accent)));
      transition: width 1s var(--mm-ease-emphasized);
    }
    .mm-progress--accent { --mm-progress-start: var(--mm-component-accent); --mm-progress-end: #f0cf8a; }
    .mm-progress--success { --mm-progress-start: var(--mm-component-success); --mm-progress-end: #86efb0; }
    .mm-progress--warning { --mm-progress-start: var(--mm-component-warning); --mm-progress-end: #f5d78e; }
    .mm-progress--info { --mm-progress-start: var(--mm-component-info); --mm-progress-end: #b6abff; }
    .mm-progress--premiere { --mm-progress-start: var(--mm-component-premiere); --mm-progress-end: #b6abff; }
    .mm-progress--violet { --mm-progress-start: var(--mm-component-premiere); --mm-progress-end: #b6abff; }
    .mm-progress--muted { --mm-progress-start: var(--mm-component-border); --mm-progress-end: var(--mm-component-border); }
    @keyframes shimmer {
      from { background-position: 180% 0; }
      to { background-position: -80% 0; }
    }
    .mm-progress__bar--live::after {
      content: '';
      position: absolute;
      inset: 0;
      border-radius: inherit;
      background: linear-gradient(100deg, transparent 20%, rgba(255, 255, 255, 0.35) 50%, transparent 80%);
      background-size: 200% 100%;
      will-change: background-position;
      animation: shimmer 1.6s linear infinite;
    }
    .mm-progress__label {
      min-width: 38px;
      color: var(--mm-component-text-secondary);
      font-size: var(--mm-text-xs);
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
    @media (prefers-reduced-motion: reduce) {
      .mm-progress__bar { transition: none; }
      .mm-progress__bar--live::after { animation: none; }
    }
  `,
})
export class MmProgress {
  readonly value = input(0);
  readonly label = input('Progress');
  readonly showLabel = input(true);
  readonly live = input(false);
  readonly tone = input<MmProgressTone>('accent');
  readonly normalized = computed(() => {
    const raw = this.value();
    if (!Number.isFinite(raw)) return 0;
    return Math.min(100, Math.max(0, raw));
  });
}
