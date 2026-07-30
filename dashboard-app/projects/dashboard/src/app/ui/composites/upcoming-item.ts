import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'mm-upcoming-item',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="up-row">
      @if (href()) {
        <a
          class="up-thumb"
          [href]="href()!"
          target="_blank"
          rel="noreferrer"
          [attr.aria-label]="'Open ' + title()"
          [style.background]="art()"
        ></a>
      } @else {
        <span class="up-thumb" aria-hidden="true" [style.background]="art()"></span>
      }
      <div class="up-copy">
        <div class="up-name" [attr.title]="title()">{{ title() }}</div>
        <div class="up-sub">{{ subtitle() }}<br />{{ airDateLabel() }}</div>
      </div>
      <span class="up-when" [class.up-when--ready]="ready()">{{ whenLabel() }}</span>
    </div>
  `,
  styleUrl: './upcoming-item.scss',
})
export class MmUpcomingItem {
  readonly title = input.required<string>();
  readonly subtitle = input('');
  readonly airDateLabel = input('');
  readonly whenLabel = input('Scheduled');
  readonly ready = input(false);
  readonly art = input('var(--mm-component-card-bg)');
  readonly href = input<string | null>(null);
}
