import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type MmTooltipPlacement = 'top' | 'bottom';
export type MmTooltipTone = 'default' | 'accent';

@Component({
  selector: 'mm-tooltip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'mm-tooltip',
    '[class.mm-tooltip--bottom]': 'placement() === "bottom"',
    '[class.mm-tooltip--accent]': 'tone() === "accent"',
  },
  template: `<span class="mm-tooltip__trigger"><ng-content /></span>
    <span class="mm-tooltip__bubble" role="tooltip">{{ text() }}</span>`,
  styles: `
    :host {
      position: relative;
      display: inline-flex;
      max-width: 100%;
    }

    .mm-tooltip__trigger {
      display: inline-flex;
      max-width: 100%;
    }

    .mm-tooltip__bubble {
      position: absolute;
      left: 50%;
      z-index: 20;
      bottom: calc(100% + 10px);
      width: max-content;
      max-width: min(220px, 70vw);
      padding: 8px 14px;
      border: 1px solid rgb(255 255 255 / 12%);
      border-radius: 9px;
      background: var(--mm-color-surface-2);
      box-shadow: 0 8px 26px rgb(0 0 0 / 50%);
      color: var(--mm-component-text-primary);
      font: 500 12px/1.25 var(--mm-font-body);
      text-align: center;
      white-space: nowrap;
      opacity: 0;
      pointer-events: none;
      transform: translate(-50%, 4px);
      transition:
        opacity var(--mm-transition-fast),
        transform var(--mm-transition-fast);
    }

    .mm-tooltip__bubble::after {
      content: '';
      position: absolute;
      left: 50%;
      top: 100%;
      width: 8px;
      height: 8px;
      border-right: 1px solid rgb(255 255 255 / 12%);
      border-bottom: 1px solid rgb(255 255 255 / 12%);
      background: inherit;
      transform: translate(-50%, -50%) rotate(45deg);
    }

    :host.mm-tooltip--bottom .mm-tooltip__bubble {
      top: calc(100% + 10px);
      bottom: auto;
      transform: translate(-50%, -4px);
    }

    :host.mm-tooltip--bottom .mm-tooltip__bubble::after {
      top: 0;
      border-right: 0;
      border-bottom: 0;
      border-left: 1px solid rgb(255 255 255 / 12%);
      border-top: 1px solid rgb(255 255 255 / 12%);
    }

    :host.mm-tooltip--accent .mm-tooltip__bubble {
      border-color: rgb(212 169 78 / 40%);
      background: color-mix(in srgb, var(--mm-component-accent) 14%, var(--mm-color-surface-2));
      color: var(--mm-component-accent);
    }

    :host:hover .mm-tooltip__bubble,
    :host:focus-within .mm-tooltip__bubble {
      opacity: 1;
      transform: translate(-50%, 0);
    }

    @media (prefers-reduced-motion: reduce) {
      .mm-tooltip__bubble {
        transition: none;
      }
    }
  `,
})
export class MmTooltip {
  /** Short label shown in the tip. Keep accessible names on the trigger itself. */
  readonly text = input.required<string>();
  readonly placement = input<MmTooltipPlacement>('top');
  readonly tone = input<MmTooltipTone>('default');
}
