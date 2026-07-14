import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MmButton, MmStateCard, MmStatus } from 'media-ui';
import { CalendarEventStatus, CalendarMediaKind } from '../downloads/media-stack-api';
import { CALENDAR_KIND_VIEW, CALENDAR_STATUS_VIEW } from './calendar-format';
import { CalendarFacade } from './calendar.facade';

@Component({
  standalone: true,
  selector: 'mm-calendar-board',
  imports: [MmButton, MmStateCard, MmStatus],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="calendar" aria-labelledby="calendar-heading">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Schedule</p>
          <h2 id="calendar-heading">Upcoming</h2>
          <p class="section-copy">Scan the next episodes and movies in your stack.</p>
        </div>
      </div>

      @if (facade.status() === 'loading') {
        <mm-state-card kind="loading" title="Loading calendar" message="Checking upcoming releases…" />
      } @else if (facade.status() === 'error') {
        <mm-state-card kind="error" title="Calendar unavailable" [message]="facade.error()" tone="danger">
          <mm-button label="Try again" (click)="retry()" />
        </mm-state-card>
      } @else if (facade.status() === 'empty') {
        <mm-state-card kind="empty" title="Nothing upcoming" message="No episodes or movies are scheduled yet." />
      } @else {
        <div class="cal-list" aria-live="polite">
          @for (event of facade.events(); track event.id) {
            <article class="cal-row">
              <span class="cal-time">{{ event.time }}</span>
              <mm-status [tone]="kindView(event.kind).tone">{{ kindView(event.kind).label }}</mm-status>
              <div class="cal-copy">
                @if (event.href) {
                  <a
                    class="cal-title cal-link"
                    [href]="event.href"
                    target="_blank"
                    rel="noreferrer"
                    [attr.title]="event.title"
                  >
                    {{ event.title }}
                    <span class="external-hint" aria-hidden="true">↗</span>
                    <span class="sr-only"> (opens in a new tab)</span>
                  </a>
                } @else {
                  <span class="cal-title" [attr.title]="event.title">{{ event.title }}</span>
                }
                <span class="cal-subtitle">{{ event.subtitle }}</span>
              </div>
              <mm-status [tone]="statusView(event.status).tone">{{ statusView(event.status).label }}</mm-status>
            </article>
          }
        </div>
      }
    </section>
  `,
  styles: `
    :host { display: block; }
    .calendar { margin-top: 0; }
    .section-heading { margin-bottom: 18px; }
    h2 { margin: 0; color: var(--mm-component-text-primary); font-size: 24px; }
    .section-copy { margin-top: 6px; color: var(--mm-component-text-secondary); font-size: 14px; }
    .cal-list { display: grid; gap: 8px; }
    .cal-row {
      display: grid;
      grid-template-columns: 64px auto minmax(0, 1fr) auto;
      align-items: center;
      gap: 12px;
      padding: 14px 16px;
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-md);
      background: var(--mm-component-card-bg);
    }
    .cal-time {
      color: var(--mm-component-text-muted);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }
    .cal-copy { display: grid; gap: 4px; min-width: 0; }
    .cal-title {
      color: var(--mm-component-text-primary);
      font-size: 14px;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .cal-link {
      color: var(--mm-component-accent);
      text-decoration: none;
    }
    .cal-link:hover,
    .cal-link:focus-visible {
      text-decoration: underline;
    }
    .external-hint {
      margin-left: 4px;
      font-weight: 700;
    }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .cal-subtitle {
      color: var(--mm-component-text-muted);
      font-size: 12px;
    }
    @container (max-width: 420px) {
      .section-copy { display: none; }
      .cal-row {
        grid-template-columns: 56px 1fr auto;
        grid-template-areas:
          "time kind status"
          "copy copy copy";
        gap: 8px;
        padding: 12px;
      }
      .cal-time { grid-area: time; }
      .cal-copy { grid-area: copy; }
    }
    @media (max-width: 850px) {
      .cal-row {
        grid-template-columns: 56px 1fr auto;
        grid-template-areas:
          "time kind status"
          "copy copy copy";
      }
      .cal-time { grid-area: time; }
      .cal-copy { grid-area: copy; }
    }
  `,
})
export class CalendarBoard {
  readonly facade = inject(CalendarFacade);

  constructor() {
    this.facade.startPolling();
  }

  kindView(kind: CalendarMediaKind) {
    return CALENDAR_KIND_VIEW[kind];
  }

  statusView(status: CalendarEventStatus) {
    return CALENDAR_STATUS_VIEW[status];
  }

  retry(): void {
    void this.facade.refresh();
  }
}
