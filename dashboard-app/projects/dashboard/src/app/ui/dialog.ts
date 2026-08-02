import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  input,
  model,
  output,
  effect,
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
  readonly showHeader = input(true);
  readonly opened = model(false);
  readonly closed = output();

  private invokingElement: HTMLElement | null = null;

  constructor() {
    effect(() => {
      const opened = this.opened();
      const dialog = this.dialogRef().nativeElement;
      if (opened && !dialog.open) {
        this.captureInvokingElement();
        this.showNativeDialog(dialog);
      } else if (!opened && dialog.open) {
        this.closeNativeDialog(dialog);
      }
    });
  }

  open(): void {
    this.captureInvokingElement();
    this.opened.set(true);
    this.showNativeDialog(this.dialogRef().nativeElement);
  }

  close(): void {
    this.opened.set(false);
    this.closeNativeDialog(this.dialogRef().nativeElement);
  }

  /** Backdrop click: only when the event target is the dialog element itself. ESC is native. */
  onDialogClick(event: MouseEvent): void {
    if (event.target === this.dialogRef().nativeElement) {
      this.close();
    }
  }

  onDialogKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Tab') return;
    const focusable = [...this.dialogRef().nativeElement.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
    )];
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  onNativeClose(): void {
    this.opened.set(false);
    this.closed.emit();
    const element = this.invokingElement;
    this.invokingElement = null;
    if (element?.isConnected) {
      queueMicrotask(() => {
        element.focus();
      });
    }
  }

  private captureInvokingElement(): void {
    const active = document.activeElement;
    if (active instanceof HTMLElement && active !== document.body && !this.dialogRef().nativeElement.contains(active)) {
      this.invokingElement = active;
    }
  }

  private showNativeDialog(dialog: HTMLDialogElement): void {
    if (dialog.open) return;
    dialog.showModal();
  }

  private closeNativeDialog(dialog: HTMLDialogElement): void {
    if (!dialog.open) return;
    dialog.close();
  }
}
