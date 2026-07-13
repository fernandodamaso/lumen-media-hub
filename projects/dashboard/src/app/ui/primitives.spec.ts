import { TestBed } from '@angular/core/testing';
import { MmButton, MmProgress, MmStateCard, MmStatus } from './primitives';

describe('media-ui primitives', () => {
  it('renders button content and preserves its base and variant classes', () => {
    const fixture = TestBed.createComponent(MmButton);
    fixture.componentRef.setInput('variant', 'quiet');
    fixture.componentRef.setInput('busy', true);
    fixture.detectChanges();
    const button = fixture.nativeElement.querySelector('button');

    expect(button.className).toContain('mm-button');
    expect(button.className).toContain('mm-button--quiet');
    expect(button.getAttribute('aria-busy')).toBe('true');
  });

  it('keeps the status base class alongside its tone class', () => {
    const fixture = TestBed.createComponent(MmStatus);
    fixture.componentRef.setInput('tone', 'danger');
    fixture.detectChanges();
    const status = fixture.nativeElement.querySelector('.mm-status');

    expect(status.classList).toContain('mm-status');
    expect(status.classList).toContain('mm-status--danger');
    expect(status.getAttribute('role')).toBe('status');
  });

  it('exposes progress semantics and the state-card danger tone', () => {
    const progress = TestBed.createComponent(MmProgress);
    progress.componentRef.setInput('value', 42);
    progress.detectChanges();
    expect(progress.nativeElement.querySelector('[role="progressbar"]').getAttribute('aria-valuenow')).toBe('42');
    expect(getComputedStyle(progress.nativeElement).display).toBe('flex');

    const state = TestBed.createComponent(MmStateCard);
    state.componentRef.setInput('tone', 'danger');
    state.detectChanges();
    expect(state.nativeElement.querySelector('.mm-state-card--danger')).toBeTruthy();
  });

  it('lets the primary button receive keyboard focus', () => {
    const fixture = TestBed.createComponent(MmButton);
    fixture.componentRef.setInput('label', 'Focus me');
    fixture.detectChanges();
    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    button.focus();
    expect(document.activeElement).toBe(button);
  });
});
