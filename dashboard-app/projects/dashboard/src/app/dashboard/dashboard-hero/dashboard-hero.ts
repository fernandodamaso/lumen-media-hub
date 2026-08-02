import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MmButtonLink, MmProgress, MmReveal } from '@app/ui';
import { HeroFacade } from './hero.facade';

@Component({
  selector: 'mm-dashboard-hero',
  imports: [MmButtonLink, MmProgress, MmReveal],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard-hero.html',
  styleUrl: './dashboard-hero.scss',
})
export class DashboardHero {
  private readonly hero = inject(HeroFacade);
  readonly view = this.hero.view;

  heroBackground(value: string): string {
    return value.includes('gradient(') || value.startsWith('url(')
      ? value
      : `url("${value}") center / cover no-repeat`;
  }
}
