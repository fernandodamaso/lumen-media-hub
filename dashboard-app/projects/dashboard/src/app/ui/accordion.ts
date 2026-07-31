import { ChangeDetectionStrategy, Component, input, signal } from '@angular/core';
import { LucideChevronDown } from '@lucide/angular';

export interface MmAccordionItem {
  id: string;
  title: string;
  content: string;
}

@Component({
  selector: 'mm-accordion',
  imports: [LucideChevronDown],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="mm-accordion">
      @for (item of items(); track item.id) {
        <div class="mm-accordion__item" [class.mm-accordion__item--open]="isOpen(item.id)">
          <button
            type="button"
            class="mm-accordion__trigger"
            [attr.aria-expanded]="isOpen(item.id)"
            (click)="toggle(item.id)"
          >
            <span>{{ item.title }}</span>
            <svg lucideChevronDown [size]="15" aria-hidden="true"></svg>
          </button>
          <div
            class="mm-accordion__panel"
            [class.mm-accordion__panel--open]="isOpen(item.id)"
            [attr.aria-hidden]="!isOpen(item.id)"
            [attr.inert]="isOpen(item.id) ? null : ''"
          >
            <div class="mm-accordion__clip">
              <div class="mm-accordion__body">{{ item.content }}</div>
            </div>
          </div>
        </div>
      }
    </div>
  `,
  styleUrl: './accordion.scss',
})
export class MmAccordion {
  readonly items = input<MmAccordionItem[]>([]);
  /** When true, only one section may be open at a time. Default multi-open per Lumen mock. */
  readonly singleOpen = input(false);
  private readonly openIds = signal<Set<string>>(new Set());

  isOpen(id: string): boolean {
    return this.openIds().has(id);
  }

  toggle(id: string): void {
    const next = new Set(this.openIds());
    if (next.has(id)) {
      next.delete(id);
    } else if (this.singleOpen()) {
      next.clear();
      next.add(id);
    } else {
      next.add(id);
    }
    this.openIds.set(next);
  }
}
