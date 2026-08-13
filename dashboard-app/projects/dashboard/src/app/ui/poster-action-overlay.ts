import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'mm-poster-action-overlay',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="mm-poster-action-overlay__poster">
      <ng-content />
    </div>
    <div class="mm-poster-action-overlay__actions" role="group" [attr.aria-label]="ariaLabel()">
      <ng-content select="mm-icon-button" />
    </div>
  `,
  styleUrl: './poster-action-overlay.scss',
})
export class MmPosterActionOverlay {
  readonly ariaLabel = input('Actions');
}
