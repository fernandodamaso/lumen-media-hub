import { ChangeDetectionStrategy, Component, ElementRef, input, output, viewChild } from '@angular/core';
import { LucideRefreshCw, LucideSearch } from '@lucide/angular';
import { MmButton } from '@app/ui';

@Component({
  selector: 'mm-dashboard-header',
  imports: [MmButton, LucideRefreshCw, LucideSearch],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard-header.html',
  styleUrl: './dashboard-header.scss',
})
export class DashboardHeader {
  readonly syncedAt = input<string>('just now');
  readonly requestMedia = output<void>();
  readonly openJellyfin = output<void>();
  readonly refresh = output<void>();
  readonly searchQuery = output<string>();

  private readonly searchInput = viewChild.required<ElementRef<HTMLInputElement>>('searchInput');

  onSearchKeydown(event: KeyboardEvent): void {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      this.focusSearch();
      return;
    }
    if (event.key === 'Enter') {
      this.searchQuery.emit((event.target as HTMLInputElement).value.trim());
    }
  }

  submitSearch(event: Event): void {
    const value = (event.target as HTMLInputElement).value.trim();
    if (value) this.searchQuery.emit(value);
  }

  focusSearch(): void {
    this.searchInput().nativeElement.focus();
  }
}
