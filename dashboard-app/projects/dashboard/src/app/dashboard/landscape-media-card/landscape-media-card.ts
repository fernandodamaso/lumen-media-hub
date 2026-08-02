import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { LucidePlay } from '@lucide/angular';
import { MmProgress } from '@app/ui';

@Component({
  selector: 'mm-landscape-media-card',
  imports: [MmProgress, LucidePlay],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <a
      class="cw-card"
      [attr.href]="href()"
      [attr.target]="href() ? '_blank' : null"
      rel="noreferrer"
      [attr.aria-label]="ariaLabel()"
    >
      <div class="cw-card__art" [style.background]="art()"></div>
      <div class="cw-shade" aria-hidden="true"></div>
      @if (showPlayCue()) {
        <span class="cw-play" aria-hidden="true">
          <svg lucidePlay [size]="15"></svg>
        </span>
      }
      <div class="cw-info">
        <div class="cw-name">{{ title() }}</div>
        @if (subtitle()) {
          <div class="cw-sub">{{ subtitle() }}</div>
        }
        @if (progressPercent() !== null) {
          <mm-progress
            class="cw-bar"
            [value]="progressPercent()!"
            [showLabel]="false"
            [label]="title() + ' watch progress'"
          />
        }
      </div>
    </a>
  `,
  styleUrl: './landscape-media-card.scss',
})
export class LandscapeMediaCard {
  readonly title = input.required<string>();
  readonly subtitle = input('');
  readonly art = input.required<string>();
  readonly href = input<string | null>(null);
  readonly ariaLabel = input.required<string>();
  readonly showPlayCue = input(false);
  readonly progressPercent = input<number | null>(null);
}
