import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  HostListener,
  inject,
  input,
  signal,
} from '@angular/core';

@Component({
  selector: 'mm-popover',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="mm-popover">
      <button type="button" class="mm-popover__trigger" [attr.aria-expanded]="open()" (click)="toggle()">
        {{ triggerLabel() }}
      </button>
      @if (open()) {
        <div class="mm-popover__panel" role="dialog">
          <ng-content />
        </div>
      }
    </div>
  `,
  styleUrl: './popover.scss',
})
export class MmPopover {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  readonly triggerLabel = input('Details');
  readonly open = signal(false);

  toggle(): void {
    this.open.update((v) => !v);
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.open()) return;
    if (!this.host.nativeElement.contains(event.target as Node)) {
      this.open.set(false);
    }
  }
}
