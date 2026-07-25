import { Routes } from '@angular/router';
import { DashboardPage } from './dashboard/dashboard-page';

export const routes: Routes = [
  { path: '', component: DashboardPage, title: 'Dashboard | Media Manager' },
  { path: 'dashboard', redirectTo: '', pathMatch: 'full' },
  {
    path: 'library',
    loadComponent: () => import('./library/library-page').then((m) => m.LibraryPage),
    title: 'Library | Media Manager',
  },
  {
    path: 'reports',
    loadComponent: () =>
      import('./reports/reports-page').then((m) => m.ReportsPage),
    title: 'Reports | Media Manager',
  },
  {
    path: 'discover',
    loadComponent: () =>
      import('./discover/discover-page').then((m) => m.DiscoverPage),
    title: 'Discover | Media Manager',
  },
  { path: '**', redirectTo: '' },
];
