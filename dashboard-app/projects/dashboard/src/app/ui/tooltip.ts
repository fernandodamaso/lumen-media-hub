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
      background: var(--mm-color-surface-elev2);
      box-shadow: var(--mm-shadow-overlay);
      color: var(--mm-component-text-primary);
      font: 500 12px/1.25 var(--mm-font-body);
      text-align: center;
      white-space: nowrap;
      opacity: 0;
      pointer-events: none;
      transform: translate(-50%, 4px);
      transition:
        opacity 0.2s,
        transform 0.2s;
    }

    .mm-tooltip__bubble::after {
      content: '';
      position: absolute;
      left: 50%;
      top: 100%;
      border-width: 5px;
      border-style: solid;
      border-color: var(--mm-color-surface-elev2) transparent transparent transparent;
      transform: translateX(-50%);
    }

    :host.mm-tooltip--bottom .mm-tooltip__bubble {
      top: calc(100% + 10px);
      bottom: auto;
      transform: translate(-50%, -4px);
    }

    :host.mm-tooltip--bottom .mm-tooltip__bubble::after {
      top: auto;
      bottom: 100%;
      border-color: transparent transparent var(--mm-color-surface-elev2) transparent;
    }

    :host.mm-tooltip--accent .mm-tooltip__bubble {
      border-color: rgb(212 169 78 / 40%);
      background: color-mix(in srgb, var(--mm-component-accent) 14%, var(--mm-color-surface-elev2));
      color: var(--mm-component-accent);
    }

    :host.mm-tooltip--accent .mm-tooltip__bubble::after {
      border-color: color-mix(in srgb, var(--mm-component-accent) 14%, var(--mm-color-surface-elev2)) transparent transparent transparent;
    }

    :host.mm-tooltip--bottom.mm-tooltip--accent .mm-tooltip__bubble::after {
      border-color: transparent transparent color-mix(in srgb, var(--mm-component-accent) 14%, var(--mm-color-surface-elev2)) transparent;
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
