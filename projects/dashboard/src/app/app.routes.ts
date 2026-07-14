import { Component } from '@angular/core';
import { Routes } from '@angular/router';
import { MmButton, MmPoster, MmProgress, MmStateCard, MmStatus } from '@app/ui';
import { DashboardPage } from './dashboard/dashboard-page';
import { DiscoverPage } from './discover/discover-page';
import { ReportsPage } from './reports/reports-page';

@Component({
  standalone: true,
  selector: 'mm-ui-catalog-page',
  imports: [MmButton, MmPoster, MmProgress, MmStateCard, MmStatus],
  template: `
  <section class="page-intro"><p class="eyebrow">Developer / media-ui</p><h1>UI catalog</h1><p class="lede">Shared primitives used by the dashboard shell.</p></section>
  <section class="catalog-section"><div class="section-heading"><div><p class="eyebrow">Foundations</p><h2>Core states</h2></div><mm-status tone="success">Ready to review</mm-status></div><div class="state-grid"><mm-state-card kind="loading" title="Loading" message="Fetching your library…"><mm-button label="Cancel" variant="quiet" /></mm-state-card><mm-state-card kind="empty" title="Empty" message="No titles have been added to this view yet." /><mm-state-card kind="error" title="Error" message="We couldn't load this collection. Try again." tone="danger"><mm-button label="Retry" /></mm-state-card></div></section>
  <section class="catalog-section"><div class="section-heading"><div><p class="eyebrow">Media</p><h2>Poster and progress</h2></div></div><div class="media-row"><mm-poster title="Afterlight" meta="2026 · Sci-fi" /><div class="progress-card"><div class="progress-copy"><strong>Afterlight</strong><span>Importing to library</span></div><div class="progress-line"><mm-progress [value]="68" label="Import progress" /></div><mm-status tone="info">Processing</mm-status></div></div></section>
`,
  styles: `.catalog-section { margin-top: 48px; } .section-heading { display: flex; align-items: end; justify-content: space-between; margin-bottom: 16px; } h2 { margin: 0; color: var(--mm-component-text-primary); font-size: 20px; } .state-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; } .media-row { display: flex; align-items: center; gap: 28px; } .progress-card { display: grid; gap: 18px; width: 360px; padding: 22px; border: 1px solid var(--mm-component-border); border-radius: var(--mm-radius-md); background: var(--mm-component-card-bg); } .progress-copy { display: grid; gap: 6px; } .progress-copy strong { color: var(--mm-component-text-primary); } .progress-copy span { color: var(--mm-component-text-muted); font-size: 13px; } .progress-line { display: flex; align-items: center; gap: 10px; }`,
})
export class UiCatalogPage {}

export const routes: Routes = [
  { path: '', component: DashboardPage, title: 'Dashboard | Media Manager' },
  { path: 'dashboard', redirectTo: '', pathMatch: 'full' },
  { path: 'reports', component: ReportsPage, title: 'Reports | Media Manager' },
  { path: 'discover', component: DiscoverPage, title: 'Discover | Media Manager' },
  { path: 'ui', component: UiCatalogPage, title: 'UI catalog | Media Manager' },
  { path: '**', redirectTo: '' },
];
