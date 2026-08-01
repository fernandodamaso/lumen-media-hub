import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { LucideSearch } from '@lucide/angular';

@Component({
  selector: 'mm-search-trigger',
  imports: [LucideSearch],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button
      type="button"
      class="mm-search-trigger"
      [disabled]="disabled()"
      [attr.data-testid]="testId()"
      [attr.aria-label]="ariaLabel() || placeholder()"
      (click)="activated.emit()"
    >
      <svg lucideSearch [size]="14" aria-hidden="true"></svg>
      <span class="mm-search-trigger__placeholder">{{ placeholder() }}</span>
      @if (shortcutLabel()) { <kbd>{{ shortcutLabel() }}</kbd> }
    </button>
  `,
  styleUrl: './search-trigger.scss',
})
export class MmSearchTrigger {
  readonly placeholder = input('Search');
  readonly shortcutLabel = input('');
  readonly ariaLabel = input('');
  readonly disabled = input(false);
  readonly testId = input('mm-search-trigger');
  readonly activated = output();
}
