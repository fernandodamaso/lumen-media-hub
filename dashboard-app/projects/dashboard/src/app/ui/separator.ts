import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'mm-separator',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { role: 'separator', '[attr.aria-orientation]': 'orientation()', class: 'mm-separator' },
  template: `@if (label()) { <span>{{ label() }}</span> }`,
  styleUrl: './separator.scss',
})
export class MmSeparator {
  readonly orientation = input<'horizontal' | 'vertical'>('horizontal');
  readonly label = input('');
}
