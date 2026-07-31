import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmLiveIndicator } from './live-indicator';

describe('MmLiveIndicator', () => {
  it('defaults to the live tone with no tone modifier class', () => {
    const fixture = TestBed.createComponent(MmLiveIndicator);
    fixture.detectChanges();
    const host = fixtureHost(fixture);
    expect(host.classList.contains('mm-live-indicator--warn')).toBe(false);
    expect(host.classList.contains('mm-live-indicator--down')).toBe(false);
  });

  it('applies the warn tone class', () => {
    const fixture = TestBed.createComponent(MmLiveIndicator);
    fixture.componentRef.setInput('tone', 'warn');
    fixture.detectChanges();
    expect(fixtureHost(fixture).classList.contains('mm-live-indicator--warn')).toBe(true);
  });

  it('applies the down tone class', () => {
    const fixture = TestBed.createComponent(MmLiveIndicator);
    fixture.componentRef.setInput('tone', 'down');
    fixture.detectChanges();
    expect(fixtureHost(fixture).classList.contains('mm-live-indicator--down')).toBe(true);
  });

  it('hides the label when compact', () => {
    const fixture = TestBed.createComponent(MmLiveIndicator);
    fixture.componentRef.setInput('compact', true);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('.mm-live-indicator__label')).toBeNull();
  });
});
