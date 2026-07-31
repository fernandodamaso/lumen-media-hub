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

@Component({
  selector: 'mm-popover',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="mm-popover">
      <button
        type="button"
        #trigger
        class="mm-popover__trigger"
        [attr.aria-expanded]="open()"
        (click)="toggle()"
      >
        {{ triggerLabel() }}
      </button>
      <div
        class="mm-popover__panel"
        role="dialog"
        [class.mm-popover__panel--open]="open()"
        [attr.aria-hidden]="!open()"
        [attr.inert]="open() ? null : ''"
      >
        <ng-content />
      </div>
    </div>
  `,
  styleUrl: './popover.scss',
})
export class MmPopover {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly triggerRef = viewChild.required<ElementRef<HTMLButtonElement>>('trigger');

  readonly triggerLabel = input('Details');
  readonly open = signal(false);
  readonly openChange = output<boolean>();

  toggle(): void {
    this.open.update((v) => !v);
    this.openChange.emit(this.open());
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.open()) return;
    if (!this.host.nativeElement.contains(event.target as Node)) {
      this.open.set(false);
      this.openChange.emit(false);
    }
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (!this.open()) return;
    this.open.set(false);
    this.openChange.emit(false);
    this.triggerRef().nativeElement.focus();
  }
}
