import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LucideInfo, LucidePlay } from '@lucide/angular';
import { MmProgress, MmReveal } from '@app/ui';
import { HeroFacade } from './hero.facade';

@Component({
  selector: 'mm-dashboard-hero',
  imports: [RouterLink, MmProgress, MmReveal, LucideInfo, LucidePlay],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard-hero.html',
  styleUrl: './dashboard-hero.scss',
})
export class DashboardHero {
  private readonly hero = inject(HeroFacade);
  readonly view = this.hero.view;
}
