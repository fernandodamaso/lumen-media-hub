import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { LucidePanelRight } from '@lucide/angular';
import { MmButton, MmIconButton, MmInput } from '@app/ui';

@Component({
  selector: 'mm-topbar',
  imports: [MmButton, MmIconButton, MmInput, LucidePanelRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="topbar">
      <mm-input
        class="search-pill"
        kind="search-pill"
        testId="topbar-search"
        placeholder="Search movies and shows…"
        ariaLabel="Search movies and shows"
        [shortcutLabel]="shortcutLabel()"
        (activated)="searchOpen.emit()"
      />
      <div class="topbar__actions">
        <mm-icon-button
          class="rail-toggle"
          data-testid="topbar-toggle-rail"
          [label]="railOpen() ? 'Hide activity rail' : 'Show activity rail'"
          [expanded]="railOpen()"
          [ariaControls]="'activity-rail'"
          (click)="railToggle.emit()"
        >
          <svg lucidePanelRight [size]="16" aria-hidden="true"></svg>
        </mm-icon-button>
        <mm-button
          data-testid="topbar-add-media"
          label="Add media"
          variant="gold"
          icon="plus"
          (click)="addMedia.emit()"
        />
      </div>
    </div>
  `,
  styleUrl: './topbar.scss',
})
export class Topbar {
  readonly shortcutLabel = input('Ctrl+K');
  readonly railOpen = input(true);
  readonly searchOpen = output();
  readonly addMedia = output();
  readonly railToggle = output();
}
