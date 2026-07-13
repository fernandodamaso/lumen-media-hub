import { DOCUMENT } from '@angular/common';
import { effect, inject, Injectable, signal } from '@angular/core';

export const MEDIA_UI_THEMES = ['nocturne', 'tokyo-night', 'github-dark-pro'] as const;
export type MediaUiTheme = (typeof MEDIA_UI_THEMES)[number];
const STORAGE_KEY = 'media-ui-theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  readonly theme = signal<MediaUiTheme>(this.readInitialTheme());

  constructor() {
    effect(() => this.applyTheme(this.theme()));
  }

  setTheme(theme: MediaUiTheme): void {
    if (MEDIA_UI_THEMES.includes(theme)) {
      this.theme.set(theme);
    }
  }

  private readInitialTheme(): MediaUiTheme {
    const bootTheme = this.document.documentElement.dataset['theme'];
    if (this.isTheme(bootTheme)) return bootTheme;
    try {
      const savedTheme = localStorage.getItem(STORAGE_KEY);
      return this.isTheme(savedTheme) ? savedTheme : 'nocturne';
    } catch {
      return 'nocturne';
    }
  }

  private persist(theme: MediaUiTheme): void {
    try { localStorage.setItem(STORAGE_KEY, theme); } catch { /* storage is optional */ }
  }

  private applyTheme(theme: MediaUiTheme): void {
    this.document.documentElement.dataset['theme'] = theme;
    this.document.documentElement.style.colorScheme = 'dark';
    this.persist(theme);
  }

  private isTheme(value: string | undefined | null): value is MediaUiTheme {
    return MEDIA_UI_THEMES.includes(value as MediaUiTheme);
  }
}
