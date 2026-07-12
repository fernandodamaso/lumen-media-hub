import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MmThemePicker, ThemeService } from 'media-ui';

@Component({
  selector: 'app-root',
  imports: [RouterLink, RouterLinkActive, RouterOutlet, MmThemePicker],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App { readonly themeService = inject(ThemeService); }
