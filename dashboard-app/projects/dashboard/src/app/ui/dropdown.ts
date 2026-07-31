import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  HostListener,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { LucideChevronDown, LucideInfo, LucideRefreshCw, LucideScanLine, LucideTrash2 } from '@lucide/angular';

type MmDropdownIcon = 'scan' | 'refresh' | 'trash' | 'info';

export interface MmDropdownItem {
  id: string;
  label: string;
  icon?: MmDropdownIcon;
  danger?: boolean;
  separatorBefore?: boolean;
}

export interface MmDropdownGroup {
  label?: string;
  items: MmDropdownItem[];
}

@Component({
  selector: 'mm-dropdown',
  imports: [LucideChevronDown, LucideInfo, LucideRefreshCw, LucideScanLine, LucideTrash2],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="mm-dropdown">
      <button
        type="button"
        #trigger
        class="mm-dropdown__trigger"
        [attr.aria-expanded]="open()"
        (click)="toggle()"
      >
        {{ triggerLabel() }}
        <svg lucideChevronDown [size]="14" aria-hidden="true"></svg>
      </button>
      <div
        class="mm-dropdown__menu"
        role="menu"
        [class.mm-dropdown__menu--open]="open()"
        [attr.aria-hidden]="!open()"
        [attr.inert]="open() ? null : ''"
      >
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
              @if (item.icon === 'scan') {
                <svg lucideScanLine [size]="15" aria-hidden="true"></svg>
              } @else if (item.icon === 'refresh') {
                <svg lucideRefreshCw [size]="15" aria-hidden="true"></svg>
              } @else if (item.icon === 'trash') {
                <svg lucideTrash2 [size]="15" aria-hidden="true"></svg>
              } @else if (item.icon === 'info') {
                <svg lucideInfo [size]="15" aria-hidden="true"></svg>
              }
              {{ item.label }}
            </button>
          }
        }
      </div>
    </div>
  `,
  styleUrl: './dropdown.scss',
})
export class MmDropdown {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly triggerRef = viewChild.required<ElementRef<HTMLButtonElement>>('trigger');

  readonly triggerLabel = input('Actions');
  readonly groups = input<MmDropdownGroup[]>([]);
  readonly open = signal(false);
  readonly itemSelect = output<MmDropdownItem>();

  toggle(): void {
    this.open.update((v) => !v);
    if (this.open()) {
      queueMicrotask(() => {
        const first = this.host.nativeElement.querySelector<HTMLElement>('[role="menuitem"]');
        first?.focus();
      });
    }
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

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (!this.open()) return;
    this.open.set(false);
    this.triggerRef().nativeElement.focus();
  }
}
