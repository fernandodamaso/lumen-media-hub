import { Component } from '@angular/core';
import { Routes } from '@angular/router';
import { MmButton, MmPoster, MmProgress, MmStateCard, MmStatus } from 'media-ui';
import { AutomationBoard } from './automation/automation-board';
import { AutomationFacade } from './automation/automation.facade';
import { CalendarBoard } from './calendar/calendar-board';
import { CalendarFacade } from './calendar/calendar.facade';
import { DownloadsBoard } from './downloads/downloads-board';
import { DownloadsFacade } from './downloads/downloads.facade';
import { LibraryBoard } from './library/library-board';
import { LibraryFacade } from './library/library.facade';
import { ReportsPage } from './reports/reports-page';

@Component({
  standalone: true,
  selector: 'mm-dashboard-page',
  imports: [CalendarBoard, DownloadsBoard, LibraryBoard, AutomationBoard],
  providers: [CalendarFacade, DownloadsFacade, LibraryFacade, AutomationFacade],
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
    <mm-library-board />
    <mm-calendar-board />
    <mm-downloads-board />
    <mm-automation-board />
  `,
})
export class DashboardPage {}

@Component({ standalone: true, selector: 'mm-discover-page', template: `<section class="page-intro"><p class="eyebrow">Workspace</p><h1>Discover</h1><p class="lede">Browse and collect new media from this space.</p></section>` })
export class DiscoverPage {}

@Component({ standalone: true, selector: 'mm-ui-catalog-page', imports: [MmButton, MmPoster, MmProgress, MmStateCard, MmStatus], template: `
  <section class="page-intro"><p class="eyebrow">Developer / media-ui</p><h1>UI catalog</h1><p class="lede">Explore the shared primitives that power the dashboard shell.</p></section>
  <section class="catalog-section"><div class="section-heading"><div><p class="eyebrow">Foundations</p><h2>Core states</h2></div><mm-status tone="success">Ready to review</mm-status></div><div class="state-grid"><mm-state-card icon="◫" title="Loading" message="Fetching your library…"><mm-button label="Cancel" variant="quiet" /></mm-state-card><mm-state-card icon="∅" title="Empty" message="No titles have been added to this view yet." /><mm-state-card icon="!" title="Error" message="We couldn't load this collection. Try again." tone="danger"><mm-button label="Retry" /></mm-state-card></div></section>
  <section class="catalog-section"><div class="section-heading"><div><p class="eyebrow">Media</p><h2>Poster and progress</h2></div></div><div class="media-row"><mm-poster title="Afterlight" meta="2026 · Sci-fi" /><div class="progress-card"><div class="progress-copy"><strong>Afterlight</strong><span>Importing to library</span></div><div class="progress-line"><mm-progress [value]="68" label="Import progress" /></div><mm-status tone="info">Processing</mm-status></div></div></section>
`, styles: `.catalog-section { margin-top: 48px; } .section-heading { display: flex; align-items: end; justify-content: space-between; margin-bottom: 16px; } h2 { margin: 0; color: var(--mm-component-text-primary); font-size: 20px; } .state-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; } .media-row { display: flex; align-items: center; gap: 28px; } .progress-card { display: grid; gap: 18px; width: 360px; padding: 22px; border: 1px solid var(--mm-component-border); border-radius: var(--mm-radius-md); background: var(--mm-component-card-bg); } .progress-copy { display: grid; gap: 6px; } .progress-copy strong { color: var(--mm-component-text-primary); } .progress-copy span { color: var(--mm-component-text-muted); font-size: 13px; } .progress-line { display: flex; align-items: center; gap: 10px; }` })
export class UiCatalogPage {}

export const routes: Routes = [
  { path: '', component: DashboardPage, title: 'Dashboard | Media Manager' },
  { path: 'dashboard', redirectTo: '', pathMatch: 'full' },
  { path: 'reports', component: ReportsPage, title: 'Reports | Media Manager' },
  { path: 'discover', component: DiscoverPage, title: 'Discover | Media Manager' },
  { path: 'ui', component: UiCatalogPage, title: 'UI catalog | Media Manager' },
  { path: '**', redirectTo: '' },
];
