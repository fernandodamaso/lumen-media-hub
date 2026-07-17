import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { LucideCalendarDays, LucideChevronRight, LucideExternalLink } from '@lucide/angular';
import { MmButton, MmCard, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { SERVICE_LINK_BASES, ServiceLinkBases } from '../media-stack/media-stack-api.providers';
import { CalendarEventStatus, CalendarMediaKind } from './calendar.models';
import { CALENDAR_KIND_VIEW, CALENDAR_STATUS_VIEW } from './calendar-format';
import { CalendarFacade } from './calendar.facade';

@Component({
  selector: 'mm-calendar-board',
  imports: [MmButton, MmCard, MmSkeleton, MmStateCard, MmStatus, LucideCalendarDays, LucideExternalLink, LucideChevronRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './calendar-board.html',
  styleUrl: './calendar-board.scss',
})
export class CalendarBoard {
  readonly facade = inject(CalendarFacade);
  private readonly linkBases = inject(SERVICE_LINK_BASES);
  readonly rowSkeletons = [0, 1, 2];

  constructor() {
    this.facade.startPolling();
  }

  calendarHref(): string | null {
    const base = (this.linkBases as ServiceLinkBases).sonarr?.replace(/\/$/, '');
    return base ? `${base}/calendar` : null;
  }

  formatTime(airDate: string, groupLabel: string): string {
    const match = airDate.match(/T(\d{2}):(\d{2})/);
    const time = match ? `${match[1]}:${match[2]}` : '—';
    if (groupLabel !== 'THIS WEEK') return time;
    const dateMatch = airDate.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!dateMatch) return time;
    const date = new Date(Number(dateMatch[1]), Number(dateMatch[2]) - 1, Number(dateMatch[3]), 12);
    const weekday = new Intl.DateTimeFormat('en', { weekday: 'short' }).format(date);
    return `${weekday} · ${time}`;
  }

  kindLabel(kind: CalendarMediaKind): string {
    return CALENDAR_KIND_VIEW[kind].label;
  }

  statusView(status: CalendarEventStatus) {
    return CALENDAR_STATUS_VIEW[status];
  }

  retry(): void {
    void this.facade.refresh();
  }
}
