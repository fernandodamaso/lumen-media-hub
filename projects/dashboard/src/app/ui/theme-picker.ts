import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { LucideCheck, LucideChevronDown } from '@lucide/angular';
import { MEDIA_UI_THEMES, ThemeService, MediaUiTheme } from './theme.service';

@Component({
  selector: 'mm-theme-picker',
  imports: [LucideCheck, LucideChevronDown],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './theme-picker.html',
  styleUrl: './theme-picker.scss',
})
export class MmThemePicker {
  readonly themeService = inject(ThemeService);
  private readonly destroyRef = inject(DestroyRef);
  readonly themes = MEDIA_UI_THEMES;
  readonly labels: Record<MediaUiTheme, string> = {
    nocturne: 'Nocturne',
    'tokyo-night': 'Tokyo Night',
    'github-dark-pro': 'GitHub Dark Pro',
  };
  readonly justSaved = signal(false);
  private savedTimeout?: ReturnType<typeof setTimeout>;

  constructor() {
    this.destroyRef.onDestroy(() => this.clearSavedTimeout());
  }

  select(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as MediaUiTheme;
    this.themeService.setTheme(value);
    this.flashSaved();
  }

  private flashSaved(): void {
    this.clearSavedTimeout();
    this.justSaved.set(true);
    this.savedTimeout = setTimeout(() => this.justSaved.set(false), 1500);
  }

  private clearSavedTimeout(): void {
    if (this.savedTimeout) {
      clearTimeout(this.savedTimeout);
      this.savedTimeout = undefined;
    }
  }
}
