import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { MmDialog } from './dialog';

@Component({
  standalone: true,
  imports: [MmDialog],
  template: `
    <mm-dialog
      #dlg
      title="Test dialog"
      tone="warning"
      [opened]="dialogOpened"
      [showHeader]="showHeader"
      (openedChange)="dialogOpened = $event"
      (closed)="onClosed()"
    >
      <p data-testid="dialog-body">Dialog body</p>
      <button type="button" mmDialogFooter>Footer action</button>
    </mm-dialog>
    <button type="button" data-testid="open" (click)="dlg.open()">Open</button>
  `,
})
class DialogHost {
  closedCount = 0;
  dialogOpened = false;
  showHeader = true;

  onClosed(): void {
    this.closedCount += 1;
  }
}

@Component({
  standalone: true,
  imports: [MmDialog],
  template: `
    <button type="button" data-testid="headerless-open" (click)="dlg.open()">Open</button>
    <mm-dialog #dlg title="Headerless dialog" [showHeader]="false"><p>Body</p></mm-dialog>
  `,
})
class HeaderlessDialogHost {}

describe('MmDialog', () => {
  let fixture: ComponentFixture<DialogHost>;
  let showModal: ReturnType<typeof vi.fn>;
  let closeFn: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    showModal = vi.fn(function (this: HTMLDialogElement) {
      this.open = true;
    });
    closeFn = vi.fn(function (this: HTMLDialogElement) {
      this.open = false;
      this.dispatchEvent(new Event('close'));
    });
    HTMLDialogElement.prototype.showModal = showModal as typeof HTMLDialogElement.prototype.showModal;
    HTMLDialogElement.prototype.close = closeFn as typeof HTMLDialogElement.prototype.close;

    TestBed.configureTestingModule({
      imports: [DialogHost, HeaderlessDialogHost],
    });
    fixture = TestBed.createComponent(DialogHost);
    fixture.detectChanges();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls showModal when open() is invoked', () => {
    fixtureHost(fixture).querySelector<HTMLButtonElement>('[data-testid="open"]')?.click();
    expect(showModal).toHaveBeenCalledTimes(1);
    expect(fixtureHost(fixture).querySelector('dialog')?.open).toBe(true);
  });

  it('does not call showModal again when the dialog is already open', () => {
    const open = fixtureHost(fixture).querySelector<HTMLButtonElement>('[data-testid="open"]');
    open?.click();
    open?.click();
    expect(showModal).toHaveBeenCalledTimes(1);
  });

  it('closes when the backdrop (dialog element) is clicked', () => {
    const dialog = fixtureHost(fixture).querySelector<HTMLDialogElement>('dialog');
    if (!dialog) throw new Error('dialog missing');
    fixtureHost(fixture).querySelector<HTMLButtonElement>('[data-testid="open"]')?.click();
    dialog.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(closeFn).toHaveBeenCalledTimes(1);
    expect(dialog.open).toBe(false);
    fixture.detectChanges();
    expect(fixture.componentInstance.closedCount).toBe(1);
  });

  it('does not close when dialog content is clicked', () => {
    const dialog = fixtureHost(fixture).querySelector<HTMLDialogElement>('dialog');
    const body = fixtureHost(fixture).querySelector<HTMLElement>('[data-testid="dialog-body"]');
    if (!dialog || !body) throw new Error('dialog content missing');
    fixtureHost(fixture).querySelector<HTMLButtonElement>('[data-testid="open"]')?.click();
    body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(closeFn).not.toHaveBeenCalled();
    expect(dialog.open).toBe(true);
  });

  it('closes when the close button is clicked', () => {
    fixtureHost(fixture).querySelector<HTMLButtonElement>('[data-testid="open"]')?.click();
    fixtureHost(fixture).querySelector<HTMLButtonElement>('.mm-dialog__close')?.click();
    expect(closeFn).toHaveBeenCalled();
    expect(fixtureHost(fixture).querySelector('dialog')?.open).toBe(false);
  });

  it('emits closed when the native dialog closes', () => {
    fixtureHost(fixture).querySelector<HTMLButtonElement>('[data-testid="open"]')?.click();
    fixtureHost(fixture).querySelector<HTMLButtonElement>('.mm-dialog__close')?.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.closedCount).toBe(1);
  });

  it('supports opened state, hides the header, and restores focus to the trigger', async () => {
    const headerlessFixture = TestBed.createComponent(HeaderlessDialogHost);
    headerlessFixture.detectChanges();
    const trigger = fixtureHost(headerlessFixture).querySelector<HTMLButtonElement>('[data-testid="headerless-open"]');
    trigger?.focus();
    trigger?.click();
    const dialogComponent = headerlessFixture.debugElement.query(By.directive(MmDialog)).componentInstance as MmDialog;
    headerlessFixture.detectChanges();
    const dialog = fixtureHost(headerlessFixture).querySelector<HTMLDialogElement>('dialog');
    expect(dialog?.getAttribute('aria-label')).toBe('Headerless dialog');
    expect(dialog?.querySelector('.mm-dialog__head')).toBeNull();
    dialogComponent.close();
    await headerlessFixture.whenStable();
    expect(document.activeElement).toBe(trigger);
  });
});
