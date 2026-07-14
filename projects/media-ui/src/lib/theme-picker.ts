import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { LucideCheck, LucideChevronDown } from '@lucide/angular';
import { MEDIA_UI_THEMES, ThemeService, MediaUiTheme } from './theme.service';

@Component({
  selector: 'mm-theme-picker',
  standalone: true,
  imports: [LucideCheck, LucideChevronDown],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <label class="picker">
      <span>Theme</span>
      <div class="picker__control">
        <select [value]="themeService.theme()" (change)="select($event)" aria-label="Choose theme">
          @for (theme of themes; track theme) {
            <option [value]="theme">{{ labels[theme] }}</option>
          }
        </select>
        @if (justSaved()) {
          <span class="picker__saved" aria-hidden="true"><svg lucideCheck [size]="13"></svg></span>
        }
        <svg class="picker__caret" lucideChevronDown [size]="16" aria-hidden="true"></svg>
      </div>
    </label>
  `,
  styles: `
    .picker {
      display: grid;
      gap: 6px;
      color: var(--mm-component-text-secondary);
      font: 700 12px/1 var(--mm-font-body);
    }
    .picker__control {
      position: relative;
      display: flex;
      align-items: center;
    }
    select {
      appearance: none;
      width: 190px;
      min-height: 40px;
      padding: 10px 34px 10px 12px;
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-sm);
      background: var(--mm-component-control-bg);
      color: var(--mm-component-text-primary);
      font: inherit;
      text-transform: capitalize;
    }
    .picker__caret {
      position: absolute;
      right: 11px;
      pointer-events: none;
    }
    .picker__saved {
      position: absolute;
      right: 32px;
      display: inline-flex;
      align-items: center;
      color: var(--mm-component-success);
      pointer-events: none;
    }
    @media (max-width: 900px), (pointer: coarse) {
      select { min-height: 44px; }
    }
  `,
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
