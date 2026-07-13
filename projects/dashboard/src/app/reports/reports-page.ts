import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MmButton, MmStateCard, MmStatus } from 'media-ui';
import { cronStatusView, formatGeneratedAt, formatRunTimestamp } from './reports-format';
import { ReportsFacade } from './reports.facade';

@Component({
  standalone: true,
  selector: 'mm-reports-page',
  imports: [MmButton, MmStateCard, MmStatus],
  providers: [ReportsFacade],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="page-intro">
      <p class="eyebrow">Workspace</p>
      <h1>Reports</h1>
      <p class="lede">Triage automation history — failed and actionable runs first, quiet successes when you need them.</p>
    </section>

    <div class="toolbar">
      @if (facade.generatedAt()) {
        <p class="generated" aria-live="polite">Generated {{ formatGeneratedAt(facade.generatedAt()) }}</p>
      } @else {
        <p class="generated muted">Waiting for first load…</p>
      }
      <mm-button
        label="Refresh"
        variant="quiet"
        [busy]="facade.refreshing()"
        [disabled]="facade.refreshing()"
        (click)="refresh()"
      />
    </div>

    @if (facade.error() && facade.status() !== 'error') {
      <p class="refresh-error" role="status" aria-live="polite">
        <mm-status tone="warning">{{ facade.error() }}</mm-status>
      </p>
    }

    @if (facade.status() === 'loading') {
      <mm-state-card icon="◌" title="Loading reports" message="Checking recent automation runs…" />
    } @else if (facade.status() === 'error') {
      <mm-state-card icon="!" title="Reports unavailable" [message]="facade.error()" tone="danger">
        <mm-button label="Try again" (click)="refresh()" />
      </mm-state-card>
    } @else if (facade.status() === 'empty') {
      <mm-state-card icon="∅" title="No cron history yet" message="Automation runs will appear here once logs are available." />
    } @else {
      @if (facade.status() === 'allClear') {
        <p class="health" role="status">
          <mm-status tone="success">All clear — {{ facade.summary().quiet }} quiet run{{ facade.summary().quiet === 1 ? '' : 's' }}.</mm-status>
        </p>
      } @else {
        <p class="health" role="status">
          <mm-status tone="warning">{{ facade.summary().actionable }} actionable run{{ facade.summary().actionable === 1 ? '' : 's' }} need attention.</mm-status>
        </p>
      }

      @if (actionableRuns().length) {
        <div class="run-list" aria-label="Actionable runs">
          @for (run of actionableRuns(); track run.id) {
            <details class="run" [open]="expanded().has(run.id)" (toggle)="onToggle(run.id, $event)">
              <summary>
                <div class="run-head">
                  <strong>{{ run.jobTitle }}</strong>
                  <mm-status [tone]="statusView(run.status).tone">{{ statusView(run.status).label }}</mm-status>
                  <span class="run-time">{{ formatRunTimestamp(run.timestamp) }}</span>
                </div>
              </summary>
              <div class="run-detail">
                @if (run.detail) {
                  <p>{{ run.detail }}</p>
                }
                @if (run.fatal) {
                  <p class="fatal">{{ run.fatal }}</p>
                }
                @if (run.applied !== null) {
                  <p>Applied {{ run.applied }}</p>
                }
              </div>
            </details>
          }
        </div>
      }

      @if (quietRuns().length) {
        <details class="quiet-section">
          <summary>{{ quietRuns().length }} quiet run{{ quietRuns().length === 1 ? '' : 's' }}</summary>
          <div class="run-list quiet-list" aria-label="Quiet runs">
            @for (run of quietRuns(); track run.id) {
              <details class="run" [open]="expanded().has(run.id)" (toggle)="onToggle(run.id, $event)">
                <summary>
                  <div class="run-head">
                    <strong>{{ run.jobTitle }}</strong>
                    <mm-status [tone]="statusView(run.status).tone">{{ statusView(run.status).label }}</mm-status>
                    <span class="run-time">{{ formatRunTimestamp(run.timestamp) }}</span>
                  </div>
                </summary>
                <div class="run-detail">
                  @if (run.detail) {
                    <p>{{ run.detail }}</p>
                  }
                </div>
              </details>
            }
          </div>
        </details>
      }
    }
  `,
  styles: `
    :host { display: block; }
    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin: 28px 0 18px;
    }
    .generated {
      margin: 0;
      color: var(--mm-component-text-secondary);
      font-size: 13px;
    }
    .generated.muted { color: var(--mm-component-text-muted); }
    .refresh-error, .health { margin: 0 0 14px; }
    .run-list { display: grid; gap: 10px; }
    .run {
      padding: 14px 16px;
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-md);
      background: var(--mm-component-card-bg);
    }
    .run > summary {
      cursor: pointer;
      list-style: none;
    }
    .run > summary::-webkit-details-marker { display: none; }
    .run-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto auto;
      align-items: center;
      gap: 12px;
    }
    .run-head strong {
      color: var(--mm-component-text-primary);
      font-size: 14px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .run-time {
      color: var(--mm-component-text-muted);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }
    .run-detail {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--mm-component-border);
      color: var(--mm-component-text-secondary);
      font-size: 13px;
    }
    .run-detail p { margin: 0 0 6px; }
    .run-detail p:last-child { margin-bottom: 0; }
    .fatal { color: var(--mm-semantic-danger, #b42318); }
    .quiet-section {
      margin-top: 20px;
      padding: 14px 16px;
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-md);
      background: var(--mm-component-card-bg);
    }
    .quiet-section > summary {
      cursor: pointer;
      color: var(--mm-component-text-secondary);
      font-size: 14px;
      font-weight: 600;
    }
    .quiet-list { margin-top: 12px; }
    @media (max-width: 700px) {
      .toolbar { flex-direction: column; align-items: start; }
      .run-head { grid-template-columns: minmax(0, 1fr) auto; }
      .run-time { grid-column: 1 / -1; }
    }
  `,
})
export class ReportsPage {
  readonly facade = inject(ReportsFacade);
  readonly formatGeneratedAt = formatGeneratedAt;
  readonly formatRunTimestamp = formatRunTimestamp;
  readonly statusView = cronStatusView;

  private readonly expandedIds = signal(new Set<string>());
  readonly expanded = this.expandedIds.asReadonly();

  readonly actionableRuns = computed(() => this.facade.runs().filter((run) => run.triage === 'actionable'));
  readonly quietRuns = computed(() => this.facade.runs().filter((run) => run.triage === 'quiet'));

  constructor() {
    void this.facade.load();
  }

  refresh(): void {
    void this.facade.refresh();
  }

  onToggle(id: string, event: Event): void {
    const open = (event.target as HTMLDetailsElement).open;
    const next = new Set(this.expandedIds());
    if (open) next.add(id);
    else next.delete(id);
    this.expandedIds.set(next);
  }
}
