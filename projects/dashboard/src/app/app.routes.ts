import { Routes } from '@angular/router';
import { DashboardPage } from './dashboard/dashboard-page';
import { DiscoverPage } from './discover/discover-page';
import { ReportsPage } from './reports/reports-page';

export const routes: Routes = [
  { path: '', component: DashboardPage, title: 'Dashboard | Media Manager' },
  { path: 'dashboard', redirectTo: '', pathMatch: 'full' },
  { path: 'reports', component: ReportsPage, title: 'Reports | Media Manager' },
  { path: 'discover', component: DiscoverPage, title: 'Discover | Media Manager' },
  { path: '**', redirectTo: '' },
];
