import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

export interface MmTabItem {
  id: string;
  label: string;
}

@Component({
  selector: 'mm-tabs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="mm-tabs" role="tablist">
      @for (tab of tabs(); track tab.id) {
        <button
          type="button"
          class="mm-tabs__tab"
          role="tab"
          [class.mm-tabs__tab--active]="active() === tab.id"
          [attr.aria-selected]="active() === tab.id"
          (click)="select(tab.id)"
        >
          {{ tab.label }}
        </button>
      }
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
