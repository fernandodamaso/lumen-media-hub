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
  template: `
    <mm-card class="calendar" labelledBy="calendar-heading">
      <div mm-card-header>
        <h2 id="calendar-heading">Upcoming</h2>
      </div>

      @if (facade.status() === 'loading') {
        <div class="cal-skeleton" aria-hidden="true">
          @for (i of rowSkeletons; track i) {
            <div class="cal-skeleton__row">
              <div class="cal-skeleton__date">
                <mm-skeleton variant="text" width="24px" />
                <mm-skeleton variant="text" width="20px" />
              </div>
              <mm-skeleton variant="text" width="70%" />
            </div>
          }
        </div>
      } @else if (facade.status() === 'error') {
        <mm-state-card kind="error" title="Calendar unavailable" [message]="facade.error()" tone="danger">
          <mm-button label="Try again" (click)="retry()" />
        </mm-state-card>
      } @else if (facade.status() === 'empty') {
        <mm-state-card kind="empty" title="Nothing upcoming" message="No episodes or movies are scheduled yet." />
      } @else {
        <div class="cal-list" aria-live="polite">
          @for (group of facade.groups(); track group.key) {
            <h3 class="date-heading">{{ group.label }}</h3>
            @for (event of group.events; track event.id) {
              <article class="cal-row">
                <div class="cal-date">
                  <span class="cal-date__day">{{ dateBlock(event.airDate).day }}</span>
                  <span class="cal-date__month">{{ dateBlock(event.airDate).month }}</span>
                </div>
                <div class="cal-copy">
                  <div class="cal-title-row">
                    @if (event.href) {
                      <a
                        class="cal-title cal-link"
                        [href]="event.href"
                        target="_blank"
                        rel="noreferrer"
                        [attr.title]="event.title"
                      >
                        {{ event.title }}
                      </a>
                    } @else {
                      <span class="cal-title" [attr.title]="event.title">{{ event.title }}</span>
                    }
                    @if (event.status === 'available') {
                      <span class="cal-status cal-status--available">
                        <span class="cal-status__dot" aria-hidden="true"></span>
                        {{ statusLabel(event.status) }}
                      </span>
                    }
                  </div>
                  <span class="cal-subtitle">{{ kindLabel(event.kind) }} · {{ formatTime(event.airDate) }} · {{ event.subtitle }}</span>
                </div>
              </article>
            }
          }
        </div>
      }
    </mm-card>
  `,
  styles: `
    :host { display: block; }
    .date-heading { margin: 14px 0 6px; color: var(--mm-component-text-muted); font-size: var(--mm-text-xs); font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
    h2 { margin: 0; color: var(--mm-component-text-primary); font-size: var(--mm-text-lg); font-weight: 700; letter-spacing: -0.01em; }
    .cal-list { display: grid; gap: 8px; }
    .cal-row {
      display: grid;
      grid-template-columns: 44px minmax(0, 1fr);
      align-items: center;
      gap: 12px;
      padding: 11px 12px;
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-md);
      background: color-mix(in srgb, var(--mm-component-raised-bg) 55%, var(--mm-component-card-bg));
    }
    .cal-date {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 2px;
      min-width: 0;
    }
    .cal-date__day {
      color: var(--mm-component-text-primary);
      font-size: 18px;
      font-weight: 800;
      line-height: 1;
      font-variant-numeric: tabular-nums;
    }
    .cal-date__month {
      color: var(--mm-component-text-muted);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: .08em;
      text-transform: uppercase;
    }
    .cal-copy { display: grid; gap: 3px; min-width: 0; }
    .cal-title-row {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }
    .cal-title {
      color: var(--mm-component-text-primary);
      font-size: var(--mm-text-md);
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .cal-link {
      color: var(--mm-component-text-primary);
      text-decoration: none;
    }
    .cal-link:hover,
    .cal-link:focus-visible {
      text-decoration: underline;
    }
    .cal-status {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      flex-shrink: 0;
      color: var(--mm-component-warning);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: .03em;
      text-transform: uppercase;
    }
    .cal-status--available { color: var(--mm-component-success); }
    .cal-status__dot {
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: currentColor;
    }
    .cal-subtitle {
      color: var(--mm-component-text-muted);
      font-size: var(--mm-text-xs);
    }
    .cal-skeleton { display: grid; gap: 8px; }
    .cal-skeleton__row {
      display: grid;
      grid-template-columns: 44px minmax(0, 1fr);
      align-items: center;
      gap: 12px;
      padding: 11px 12px;
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-md);
      background: color-mix(in srgb, var(--mm-component-raised-bg) 55%, var(--mm-component-card-bg));
    }
    .cal-skeleton__date { display: flex; flex-direction: column; gap: 4px; }
    @container (max-width: 420px) {
      .cal-row,
      .cal-skeleton__row {
        grid-template-columns: 38px minmax(0, 1fr);
        gap: 10px;
        padding: 10px;
      }
    }
    @media (max-width: 850px) {
      .cal-row,
      .cal-skeleton__row {
        grid-template-columns: 38px minmax(0, 1fr);
        gap: 10px;
        padding: 10px;
      }
    }
  `,
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
