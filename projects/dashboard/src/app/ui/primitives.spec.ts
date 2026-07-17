import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MmButton, MmCard, MmProgress, MmStateCard, MmStatus } from './index';

@Component({
  standalone: true,
  imports: [MmCard],
  template: `<mm-card labelledBy="test-heading">
    <h2 mm-card-header id="test-heading">Library</h2>
    <button mm-card-header-actions type="button">Filter</button>
    <p>Card body</p>
    <span mm-card-footer>8 items shown</span>
    <a mm-card-footer-actions href="/library">View all</a>
  </mm-card>`,
})
class CardRegionsHost {}

@Component({
  standalone: true,
  imports: [MmCard],
  template: `<mm-card><p>Body only</p></mm-card>`,
})
class BodyOnlyCardHost {}

@Component({
  standalone: true,
  imports: [MmCard],
  template: `<mm-card>
    <p>Card body</p>
    <ng-container mm-card-footer><span>8 items shown</span></ng-container>
    <ng-container mm-card-footer-actions><a href="/library">View all</a></ng-container>
  </mm-card>`,
})
class ContainerRegionsHost {}

describe('app/ui primitives', () => {
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

  it('renders optional card regions and omits empty header and footer chrome', () => {
    const complete = TestBed.createComponent(CardRegionsHost);
    complete.detectChanges();
    expect(complete.nativeElement.querySelector('.mm-card__header')?.textContent).toContain('Library');
    expect(complete.nativeElement.querySelector('.mm-card__footer')?.textContent).toContain('8 items shown');
    expect(complete.nativeElement.querySelector('.mm-card')?.getAttribute('aria-labelledby')).toBe('test-heading');

    const bodyOnly = TestBed.createComponent(BodyOnlyCardHost);
    bodyOnly.detectChanges();
    expect(getComputedStyle(bodyOnly.nativeElement.querySelector('.mm-card__header')).display).toBe('none');
    expect(getComputedStyle(bodyOnly.nativeElement.querySelector('.mm-card__footer')).display).toBe('none');

    const containerRegions = TestBed.createComponent(ContainerRegionsHost);
    containerRegions.detectChanges();
    const projectedFooter = containerRegions.nativeElement.querySelector('.mm-card__footer') as HTMLElement;
    expect(projectedFooter.hidden).toBe(false);
    expect(projectedFooter.textContent).toContain('8 items shown');
    expect(projectedFooter.textContent).toContain('View all');
  });

  it('keeps shared buttons at least 40px high', () => {
    const fixture = TestBed.createComponent(MmButton);
    fixture.detectChanges();

    expect(getComputedStyle(fixture.nativeElement.querySelector('button')).minHeight).toBe('40px');
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
});
