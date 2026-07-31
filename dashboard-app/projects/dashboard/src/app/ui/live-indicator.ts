import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type MmLiveIndicatorTone = 'live' | 'ok' | 'warn' | 'down';

@Component({
  selector: 'mm-live-indicator',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'mm-live-indicator',
    role: 'img',
    '[class.mm-live-indicator--ok]': 'tone() === "ok"',
    '[class.mm-live-indicator--warn]': 'tone() === "warn"',
    '[class.mm-live-indicator--down]': 'tone() === "down"',
    '[class.mm-live-indicator--reduced]': 'reduced()',
    '[attr.aria-label]': 'label()',
  },
  template: `<span class="mm-live-indicator__dot"></span>
    @if (!compact()) {
      <span class="mm-live-indicator__label">{{ label() }}</span>
    }`,
  styleUrl: './live-indicator.scss',
})
export class MmLiveIndicator {
  /** 'live' pulses green (mock default); ok/warn/down are static status lamps. */
  readonly tone = input<MmLiveIndicatorTone>('live');
  readonly label = input('Live');
  readonly compact = input(false);
  readonly reduced = input(false);
}
