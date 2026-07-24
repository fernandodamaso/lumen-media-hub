import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { LucideCalendarDays, LucideChevronRight, LucideExternalLink } from '@lucide/angular';
import { MmButton, MmCard, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { CalendarMediaKind } from './calendar.models';
import { CALENDAR_KIND_VIEW } from './calendar-format';
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
    const base = (this.linkBases).sonarr?.replace(/\/$/, '');
    return base ? `${base}/calendar` : null;
  }

  formatTime(airDate: string, _groupLabel?: string): string {
    const match = /T(\d{2}):(\d{2})/.exec(airDate);
    return match ? `${match[1]}:${match[2]}` : '—';
  }

  kindLabel(kind: CalendarMediaKind): string {
    return CALENDAR_KIND_VIEW[kind].label;
  }

  retry(): void {
    void this.facade.refresh({ initial: true });
  }
}
