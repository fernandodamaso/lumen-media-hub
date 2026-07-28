import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { LucideChevronRight } from '@lucide/angular';
import { MmButton, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { CalendarEventStatus, CalendarMediaKind } from './calendar.models';
import { CALENDAR_KIND_VIEW, CALENDAR_STATUS_VIEW } from './calendar-format';
import { CalendarFacade } from './calendar.facade';

@Component({
  selector: 'mm-upcoming-card',
  imports: [MmButton, MmSkeleton, MmStateCard, MmStatus, LucideChevronRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './upcoming-card.html',
  styleUrl: './upcoming-card.scss',
})
export class UpcomingCard {
  readonly facade = inject(CalendarFacade);
  private readonly linkBases = inject(SERVICE_LINK_BASES);
  readonly rowSkeletons = [0, 1, 2, 3];

  constructor() {
    this.facade.startPolling();
  }

  calendarHref(): string | null {
    const base = this.linkBases.sonarr?.replace(/\/$/, '');
    return base ? `${base}/calendar` : null;
  }

  dayLabel(label: string): string {
    if (label === 'TODAY') return 'Today';
    if (label === 'TOMORROW') return 'Tomorrow';
    return label.charAt(0) + label.slice(1).toLowerCase();
  }

  formatTime(airDate: string): string {
    const date = new Date(airDate);
    if (Number.isNaN(date.getTime())) return '—';
    return new Intl.DateTimeFormat(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(date);
  }

  kindLabel(kind: CalendarMediaKind): string {
    return CALENDAR_KIND_VIEW[kind].label;
  }

  statusView(status: CalendarEventStatus) {
    return CALENDAR_STATUS_VIEW[status];
  }

  retry(): void {
    void this.facade.refresh({ initial: true });
  }
}
