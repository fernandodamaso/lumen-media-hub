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
    <section class="page-intro region region--intro">
      <p class="eyebrow">Overview</p>
      <h1>Dashboard</h1>
      <p class="lede">Library, downloads, automation, and upcoming releases.</p>
    </section>

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
      gap: 24px;
      margin-top: 24px;
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
      opacity: 0;
      transform: translateY(8px);
      animation: region-enter 180ms ease-out forwards;
    }

    .home-grid > .region > * {
      display: block;
      height: 100%;
    }

    .region--intro {
      animation-delay: 0ms;
    }

    .region--library {
      animation-delay: 40ms;
    }

    .region--calendar {
      animation-delay: 80ms;
    }

    .region--downloads {
      animation-delay: 120ms;
    }

    .region--automation {
      animation-delay: 160ms;
    }

    @keyframes region-enter {
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    @media (max-width: 1279px) {
      .home-grid {
        grid-template-columns: 1fr;
      }
      .home-grid > * { grid-column: 1; grid-row: auto; }
    }

    @media (prefers-reduced-motion: reduce) {
      .region {
        opacity: 1;
        transform: none;
        animation: none;
      }
    }
  `,
})
export class DashboardPage {}
