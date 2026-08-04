import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LucideCircleAlert, LucideCircleCheck, LucideDownload, LucideTrash2 } from '@lucide/angular';
import { MmSkeleton } from '@app/ui';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { MmServiceRow } from '../automation/service-row';
import { AUTOMATION_SERVICE_STATUS_VIEW, formatRelativeTime } from '../automation/automation-format';
import { AutomationServiceStatus, compareAutomationServices } from '../automation/automation.models';
import { serviceIconPath } from '../automation/service-catalog';
import { CalendarFacade, CalendarRailEvent } from '../calendar/calendar.facade';
import { MmUpcomingItem } from '../calendar/upcoming-item';
import { DEFAULT_LIBRARY_ART } from '../library/library.models';
import { ActivityItem } from '../activity/activity.models';
import { SERVICE_LINK_BASES } from '../media-stack/media-stack-api.providers';
import { ActivityFacade } from './activity.facade';

type ActivityTone = 'dl' | 'ok' | 'del' | 'fail';

@Component({
  selector: 'mm-right-rail',
  imports: [
    RouterLink,
    MmSkeleton,
    MmUpcomingItem,
    MmServiceRow,
    LucideCircleAlert,
    LucideCircleCheck,
    LucideDownload,
    LucideTrash2,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './right-rail.html',
  styleUrl: './right-rail.scss',
})
export class RightRail {
  readonly calendar = inject(CalendarFacade);
  readonly activity = inject(ActivityFacade);
  readonly health = inject(ServiceHealthFacade);
  private readonly linkBases = inject(SERVICE_LINK_BASES);

  readonly skeletonRows = [0, 1, 2];
  readonly fallbackArt = DEFAULT_LIBRARY_ART;

  readonly upcoming = computed(() => this.calendar.events().slice(0, 4));

  readonly services = computed(() => [...this.health.services()].sort(compareAutomationServices));

  readonly allGood = computed(
    () => !this.health.error() && this.services().length > 0 && this.health.health().overall === 'healthy',
  );

  calendarHref(): string | null {
    const base = this.linkBases.sonarr?.replace(/\/$/, '');
    return base ? `${base}/calendar` : null;
  }

  whenLabel(event: CalendarRailEvent): string {
    if (event.status === 'available') return 'Ready';
    return formatRelativeTime(event.airDate) || 'Scheduled';
  }

  formatAirDate(airDate: string): string {
    const date = new Date(airDate);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  activityTone(item: ActivityItem): ActivityTone {
    switch (item.kind) {
      case 'grabbed':
        return 'dl';
      case 'imported':
        return 'ok';
      case 'deleted':
        return 'del';
      case 'failed':
        return 'fail';
    }
  }

  formatWhen(timestamp: string): string {
    return formatRelativeTime(timestamp);
  }

  statusLabel(status: AutomationServiceStatus): string {
    return AUTOMATION_SERVICE_STATUS_VIEW[status].label;
  }

  serviceInitial(name: string): string {
    return (name.charAt(0) || '?').toUpperCase();
  }

  serviceIcon(id: string): string | null {
    return serviceIconPath(id);
  }
}
