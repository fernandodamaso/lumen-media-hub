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
      <p class="lede">Library first, operations beside it, and upcoming media in a supporting rail.</p>
    </section>

    <div class="home-grid" data-testid="home-grid">
      <div class="home-grid__library region region--library" data-region="library">
        <mm-library-board />
      </div>
      <div class="home-grid__downloads region region--downloads" data-region="downloads">
        <mm-downloads-board />
      </div>
      <div class="home-grid__automation region region--automation" data-region="automation">
        <mm-automation-board />
      </div>
      <div class="home-grid__calendar region region--calendar" data-region="calendar">
        <mm-calendar-board />
      </div>
    </div>
  `,
  styles: `
    :host {
      display: block;
    }

    .home-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr) minmax(280px, 320px);
      grid-template-rows: auto auto;
      grid-template-areas:
        'library library calendar'
        'downloads automation calendar';
      gap: 28px;
      margin-top: 36px;
      align-items: start;
    }

    .home-grid__library {
      grid-area: library;
      min-width: 0;
    }

    .home-grid__downloads {
      grid-area: downloads;
      min-width: 0;
      container-type: inline-size;
    }

    .home-grid__automation {
      grid-area: automation;
      min-width: 0;
      container-type: inline-size;
    }

    .home-grid__calendar {
      grid-area: calendar;
      min-width: 0;
      container-type: inline-size;
      position: sticky;
      top: 24px;
    }

    .region {
      opacity: 0;
      transform: translateY(8px);
      animation: region-enter 180ms ease-out forwards;
    }

    .region--intro {
      animation-delay: 0ms;
    }

    .region--library {
      animation-delay: 40ms;
    }

    .region--downloads {
      animation-delay: 80ms;
    }

    .region--automation {
      animation-delay: 120ms;
    }

    .region--calendar {
      animation-delay: 160ms;
    }

    @keyframes region-enter {
      to {
        opacity: 1;
        transform: translateY(0);
      }
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
