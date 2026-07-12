import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'mm-media-ui',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="media-ui-badge">{{ label() }}</span>`,
  styles: `
    :host { display: inline-block; }
    .media-ui-badge { display: inline-block; padding: 4px 8px; border-radius: 999px; background: #edf1ff; color: #2347d6; font: 600 12px/1.2 system-ui, sans-serif; }
  `,
})
export class MediaUi {
  readonly label = input('Media UI');
}
