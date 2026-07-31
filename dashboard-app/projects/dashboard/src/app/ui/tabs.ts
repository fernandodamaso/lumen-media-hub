import { ChangeDetectionStrategy, Component, computed, inject, input, model } from '@angular/core';

export interface MmTabItem {
  id: string;
  label: string;
}

@Component({
  selector: 'mm-tabs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="mm-tabs">
      <div class="mm-tabs__list" role="tablist">
        @for (tab of tabs(); track tab.id) {
          <button
            type="button"
            class="mm-tabs__tab"
            role="tab"
            [class.mm-tabs__tab--active]="active() === tab.id"
            [attr.aria-selected]="active() === tab.id"
            [attr.tabindex]="active() === tab.id ? 0 : -1"
            (click)="select(tab.id)"
          >
            {{ tab.label }}
          </button>
        }
      </div>
      <div class="mm-tabs__panel">
        <ng-content />
      </div>
    </div>
  `,
  styleUrl: './tabs.scss',
})
export class MmTabs {
  readonly tabs = input<MmTabItem[]>([]);
  readonly active = model('');

  select(id: string): void {
    this.active.set(id);
  }
}

@Component({
  selector: 'mm-tab-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'mm-tab-panel',
    '[class.mm-tab-panel--active]': 'isActive()',
    '[attr.aria-hidden]': '!isActive()',
    '[attr.inert]': 'isActive() ? null : ""',
    role: 'tabpanel',
  },
  template: `<ng-content />`,
})
export class MmTabPanel {
  readonly panelId = input.required<string>();
  private readonly tabs = inject(MmTabs);
  readonly isActive = computed(() => this.tabs.active() === this.panelId());
}
