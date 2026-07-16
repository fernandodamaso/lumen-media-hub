import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { LucideCompass, LucideFileText, LucideLayoutDashboard } from '@lucide/angular';
import { MmThemePicker, ThemeService } from '@app/ui';

import { environment } from '../environments/environment';

@Component({
  selector: 'app-root',
  imports: [RouterLink, RouterLinkActive, RouterOutlet, MmThemePicker, LucideLayoutDashboard, LucideFileText, LucideCompass],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  readonly themeService = inject(ThemeService);
  readonly modeLabel = environment.modeLabel;
}
