import { ChangeDetectionStrategy, Component } from '@angular/core';
import { AutomationBoard } from '../automation/automation-board';
import { AutomationFacade } from '../automation/automation.facade';
import { CalendarBoard } from '../calendar/calendar-board';
import { CalendarFacade } from '../calendar/calendar.facade';
import { DownloadsBoard } from '../downloads/downloads-board';
import { DownloadsFacade } from '../downloads/downloads.facade';
import { LibraryBoard } from '../library/library-board';
import { LibraryFacade } from '../library/library.facade';

@Component({
  standalone: true,
  selector: 'mm-dashboard-page',
  imports: [CalendarBoard, DownloadsBoard, LibraryBoard, AutomationBoard],
  providers: [CalendarFacade, DownloadsFacade, LibraryFacade, AutomationFacade],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1 class="sr-only">Dashboard</h1>
    <div class="home-grid" data-testid="home-grid">
      <div class="home-grid__library region region--library" data-region="library">
        <mm-library-board />
      </div>
      <div class="home-grid__calendar region region--calendar" data-region="calendar">
        <mm-calendar-board />
      </div>
      <div class="home-grid__downloads region region--downloads" data-region="downloads">
        <mm-downloads-board />
      </div>
      <div class="home-grid__automation region region--automation" data-region="automation">
        <mm-automation-board />
      </div>
    </div>
  `,
  styles: `
    :host {
      display: block;
    }

    .home-grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 20px;
      align-items: stretch;
    }

    .home-grid__library {
      grid-column: 1 / span 8;
      min-width: 0;
      container-type: inline-size;
    }

    .home-grid__downloads {
      grid-column: 1 / span 7;
      min-width: 0;
      container-type: inline-size;
    }

    .home-grid__automation {
      grid-column: 8 / span 5;
      min-width: 0;
      container-type: inline-size;
    }

    .home-grid__calendar {
      grid-column: 9 / span 4;
      grid-row: 1;
      min-width: 0;
      container-type: inline-size;
    }

    .region {
      min-width: 0;
      opacity: 1;
    }

    .home-grid > .region > * {
      display: block;
      height: 100%;
    }

    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }

    @media (max-width: 1279px) {
      .home-grid {
        grid-template-columns: 1fr;
      }
      .home-grid > * { grid-column: 1; grid-row: auto; }
    }
  `,
})
export class DashboardPage {}
