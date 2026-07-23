import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MetricCard } from './metric-card';

describe('MetricCard', () => {
  it('applies the tone class and renders MmProgress for storage', () => {
    const fixture = TestBed.createComponent(MetricCard);
    fixture.componentRef.setInput('tone', 'warning');
    fixture.componentRef.setInput('label', 'Storage');
    fixture.componentRef.setInput('value', '78%');
    fixture.componentRef.setInput('progress', 78);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('.metric-card--warning')).toBeTruthy();
    expect(root.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('78');
  });
});
