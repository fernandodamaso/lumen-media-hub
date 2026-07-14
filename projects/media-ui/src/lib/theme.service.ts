import { DOCUMENT } from '@angular/common';
import { computed, effect, inject, Injectable, signal } from '@angular/core';

export const MEDIA_UI_THEMES = ['nocturne', 'tokyo-night', 'github-dark-pro'] as const;
export type MediaUiTheme = (typeof MEDIA_UI_THEMES)[number];
const STORAGE_KEY = 'media-ui-theme';

const THEME_SURFACE_COLOR: Record<MediaUiTheme, string> = {
  nocturne: '#0b0e14',
  'tokyo-night': '#16161e',
  'github-dark-pro': '#0d1117',
};

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  readonly theme = signal<MediaUiTheme>(this.readInitialTheme());
  readonly themes = MEDIA_UI_THEMES;
  readonly themeLabel = computed(() => this.theme().replaceAll('-', ' '));

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
      return this.isTheme(savedTheme) ? savedTheme : 'github-dark-pro';
    } catch {
      return 'github-dark-pro';
    }
  }

  private persist(theme: MediaUiTheme): void {
    try { localStorage.setItem(STORAGE_KEY, theme); } catch { /* storage is optional */ }
  }

  private applyTheme(theme: MediaUiTheme): void {
    this.document.documentElement.dataset['theme'] = theme;
    this.document.documentElement.style.colorScheme = 'dark';
    this.updateThemeColor(THEME_SURFACE_COLOR[theme]);
    this.persist(theme);
  }

  private updateThemeColor(color: string): void {
    const meta = this.document.querySelector('meta[name="theme-color"]') as HTMLMetaElement | null;
    if (meta) {
      meta.setAttribute('content', color);
    }
  }

  private isTheme(value: string | undefined | null): value is MediaUiTheme {
    return MEDIA_UI_THEMES.includes(value as MediaUiTheme);
  }
}
