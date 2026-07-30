import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { LucideSearch } from '@lucide/angular';
import { MmButton } from '@app/ui';

@Component({
  selector: 'mm-topbar',
  imports: [MmButton, LucideSearch],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="topbar">
      <button type="button" class="search-pill" data-testid="topbar-search" (click)="searchOpen.emit()">
        <svg lucideSearch [size]="14" aria-hidden="true"></svg>
        <span class="search-pill__placeholder">Search movies, shows, people…</span>
        <kbd>{{ shortcutLabel() }}</kbd>
      </button>
      <div class="topbar__actions">
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
  readonly searchOpen = output();
  readonly addMedia = output();
}
