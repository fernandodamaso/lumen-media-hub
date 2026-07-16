import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { LucideCalendarDays } from '@lucide/angular';
import { MmButton, MmCard, MmSkeleton, MmStateCard } from '@app/ui';
import { CalendarEventStatus, CalendarMediaKind } from './calendar.models';
import { CALENDAR_KIND_VIEW, CALENDAR_STATUS_VIEW } from './calendar-format';
import { CalendarFacade } from './calendar.facade';

@Component({
  selector: 'mm-calendar-board',
  imports: [MmButton, MmCard, MmSkeleton, MmStateCard, LucideCalendarDays],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './calendar-board.html',
  styleUrl: './calendar-board.scss',
})
export class CalendarBoard {
  readonly facade = inject(CalendarFacade);
  readonly rowSkeletons = [0, 1, 2];

  constructor() {
    this.facade.startPolling();
  }

  formatTime(airDate: string): string {
    const match = airDate.match(/T(\d{2}):(\d{2})/);
    return match ? `${match[1]}:${match[2]}` : '—';
  }

  kindLabel(kind: CalendarMediaKind): string {
    return CALENDAR_KIND_VIEW[kind].label;
  }

  statusLabel(status: CalendarEventStatus): string {
    return CALENDAR_STATUS_VIEW[status].label;
  }

  retry(): void {
    void this.facade.refresh();
  }
}
