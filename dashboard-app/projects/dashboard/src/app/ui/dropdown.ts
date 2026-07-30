import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  HostListener,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

export interface MmDropdownItem {
  id: string;
  label: string;
  danger?: boolean;
  separatorBefore?: boolean;
}

export interface MmDropdownGroup {
  label?: string;
  items: MmDropdownItem[];
}

@Component({
  selector: 'mm-dropdown',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="mm-dropdown">
      <button
        type="button"
        class="mm-dropdown__trigger"
        [attr.aria-expanded]="open()"
        (click)="toggle()"
      >
        {{ triggerLabel() }}
      </button>
      @if (open()) {
        <div class="mm-dropdown__menu" role="menu">
          @for (group of groups(); track $index) {
            @if (group.label) {
              <div class="mm-dropdown__group-label">{{ group.label }}</div>
            }
            @for (item of group.items; track item.id) {
              @if (item.separatorBefore) {
                <div class="mm-dropdown__sep" role="separator"></div>
              }
              <button
                type="button"
                class="mm-dropdown__item"
                [class.mm-dropdown__item--danger]="item.danger"
                role="menuitem"
                (click)="pick(item)"
              >
                {{ item.label }}
              </button>
            }
          }
        </div>
      }
    </div>
  `,
  styleUrl: './dropdown.scss',
})
export class MmDropdown {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  readonly triggerLabel = input('Actions');
  readonly groups = input<MmDropdownGroup[]>([]);
  readonly open = signal(false);
  readonly itemSelect = output<MmDropdownItem>();

  toggle(): void {
    this.open.update((v) => !v);
  }

  pick(item: MmDropdownItem): void {
    this.itemSelect.emit(item);
    this.open.set(false);
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.open()) return;
    if (!this.host.nativeElement.contains(event.target as Node)) {
      this.open.set(false);
    }
  }
}
