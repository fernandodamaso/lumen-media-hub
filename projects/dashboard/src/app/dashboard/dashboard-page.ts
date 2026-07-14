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
  templateUrl: './dashboard-page.html',
  styleUrl: './dashboard-page.scss',
})
export class DashboardPage {}
