import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type MmProgressTone = 'accent' | 'success' | 'warning' | 'info' | 'premiere';

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
      <div class="mm-progress__bar" [style.width.%]="normalized()"></div>
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
      height: var(--mm-progress-height, 8px);
      overflow: hidden;
      flex: 1;
      border-radius: 999px;
      background: var(--mm-component-border);
    }
    .mm-progress__bar {
      height: 100%;
      border-radius: inherit;
      background: var(--mm-progress-tone, var(--mm-component-accent));
      transition: width var(--mm-transition-normal);
    }
    .mm-progress--accent { --mm-progress-tone: var(--mm-component-accent); }
    .mm-progress--success { --mm-progress-tone: var(--mm-component-success); }
    .mm-progress--warning { --mm-progress-tone: var(--mm-component-warning); }
    .mm-progress--info { --mm-progress-tone: var(--mm-component-info); }
    .mm-progress--premiere { --mm-progress-tone: var(--mm-component-premiere); }
    .mm-progress__label {
      min-width: 38px;
      color: var(--mm-component-text-secondary);
      font-size: var(--mm-text-xs);
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
    @media (prefers-reduced-motion: reduce) {
      .mm-progress__bar { transition: none; }
    }
  `,
})
export class MmProgress {
  readonly value = input(0);
  readonly label = input('Progress');
  readonly showLabel = input(true);
  readonly tone = input<MmProgressTone>('accent');
  readonly normalized = computed(() => {
    const raw = this.value();
    if (!Number.isFinite(raw)) return 0;
    return Math.min(100, Math.max(0, raw));
  });
}
