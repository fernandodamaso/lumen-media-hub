import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  input,
  output,
  viewChild,
} from '@angular/core';
import { LucideX } from '@lucide/angular';

export type MmDialogTone = 'default' | 'warning' | 'danger';

let nextDialogTitleId = 0;

@Component({
  selector: 'mm-dialog',
  imports: [LucideX],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dialog.html',
  styleUrl: './dialog.scss',
})
export class MmDialog {
  private readonly dialogRef = viewChild.required<ElementRef<HTMLDialogElement>>('dialogEl');

  readonly dialogId = `mm-dialog-${++nextDialogTitleId}`;
  readonly titleId = `${this.dialogId}-title`;
  readonly title = input('Dialog');
  readonly tone = input<MmDialogTone>('default');
  readonly closed = output();

  open(): void {
    this.dialogRef().nativeElement.showModal();
  }

  close(): void {
    this.dialogRef().nativeElement.close();
  }

  /** Backdrop click: only when the event target is the dialog element itself. ESC is native. */
  onDialogClick(event: MouseEvent): void {
    if (event.target === this.dialogRef().nativeElement) {
      this.close();
    }
  }

  onNativeClose(): void {
    this.closed.emit();
  }
}
