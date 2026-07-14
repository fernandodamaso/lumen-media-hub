import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { LucideCheck, LucideChevronDown } from '@lucide/angular';
import { MEDIA_UI_THEMES, ThemeService, MediaUiTheme } from './theme.service';

@Component({
  selector: 'mm-theme-picker',
  standalone: true,
  imports: [LucideCheck, LucideChevronDown],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './theme-picker.html',
  styleUrl: './theme-picker.scss',
})
export class MmThemePicker {
  readonly themeService = inject(ThemeService);
  readonly themes = MEDIA_UI_THEMES;
  readonly labels: Record<MediaUiTheme, string> = {
    nocturne: 'Nocturne',
    'tokyo-night': 'Tokyo Night',
    'github-dark-pro': 'GitHub Dark Pro',
  };
  readonly justSaved = signal(false);
  private savedTimeout?: ReturnType<typeof setTimeout>;

  select(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as MediaUiTheme;
    this.themeService.setTheme(value);
    this.flashSaved();
  }

  private flashSaved(): void {
    if (this.savedTimeout) clearTimeout(this.savedTimeout);
    this.justSaved.set(true);
    this.savedTimeout = setTimeout(() => this.justSaved.set(false), 1500);
  }
}
