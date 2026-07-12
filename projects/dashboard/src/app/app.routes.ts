import { Component } from '@angular/core';
import { Routes } from '@angular/router';

@Component({
  standalone: true,
  selector: 'mm-dashboard-page',
  template: `
    <section class="page-intro">
      <p class="eyebrow">Overview</p>
      <h1>Dashboard</h1>
      <p class="lede">Your media workspace is ready for the next slice.</p>
    </section>
    <div class="metric-grid">
      <article><span>Library health</span><strong>Ready</strong></article>
      <article><span>Active workflows</span><strong>0</strong></article>
      <article><span>Last sync</span><strong>Not connected</strong></article>
    </div>
  `,
})
export class DashboardPage {}

@Component({ standalone: true, selector: 'mm-reports-page', template: `<section class="page-intro"><p class="eyebrow">Workspace</p><h1>Reports</h1><p class="lede">Reporting tools will live here.</p></section>` })
export class ReportsPage {}

@Component({ standalone: true, selector: 'mm-discover-page', template: `<section class="page-intro"><p class="eyebrow">Workspace</p><h1>Discover</h1><p class="lede">Browse and collect new media from this space.</p></section>` })
export class DiscoverPage {}

@Component({ standalone: true, selector: 'mm-ui-catalog-page', template: `<section class="page-intro"><p class="eyebrow">Developer</p><h1>UI catalog</h1><p class="lede">Shared media-ui components will be catalogued here.</p></section>` })
export class UiCatalogPage {}

export const routes: Routes = [
  { path: '', component: DashboardPage, title: 'Dashboard | Media Manager' },
  { path: 'dashboard', redirectTo: '', pathMatch: 'full' },
  { path: 'reports', component: ReportsPage, title: 'Reports | Media Manager' },
  { path: 'discover', component: DiscoverPage, title: 'Discover | Media Manager' },
  { path: 'ui', component: UiCatalogPage, title: 'UI catalog | Media Manager' },
  { path: '**', redirectTo: '' },
];
