import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MmButton, MmCard, MmSkeleton, MmStateCard } from '@app/ui';
import { CalendarEventStatus, CalendarMediaKind } from '../media-stack/media-stack-api';
import { CALENDAR_KIND_VIEW, CALENDAR_STATUS_VIEW } from './calendar-format';
import { CalendarFacade } from './calendar.facade';

@Component({
  standalone: true,
  selector: 'mm-calendar-board',
  imports: [MmButton, MmCard, MmSkeleton, MmStateCard],
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

  dateBlock(airDate: string): { day: string; month: string } {
    const match = airDate.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!match) return { day: '--', month: '---' };
    const [, , monthNum, day] = match;
    const date = new Date(2000, Number(monthNum) - 1, 1);
    const month = new Intl.DateTimeFormat('en', { month: 'short' }).format(date);
    return { day: String(Number(day)), month: month.toUpperCase() };
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
