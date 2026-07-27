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

  it('replaces value chrome with shimmer skeletons while loading', () => {
    const fixture = TestBed.createComponent(MetricCard);
    fixture.componentRef.setInput('label', 'Library');
    fixture.componentRef.setInput('value', '0');
    fixture.componentRef.setInput('meta', '0 movies · 0 series');
    fixture.componentRef.setInput('loading', true);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelectorAll('mm-skeleton').length).toBeGreaterThan(0);
    expect(root.querySelector('.metric-card--skeleton')?.getAttribute('aria-busy')).toBe('true');
    expect(root.textContent).not.toContain('0 movies');
    expect(root.querySelector('.metric-card__value')).toBeNull();
  });

  it('reveals loaded metric content without the legacy enter class', () => {
    const fixture = TestBed.createComponent(MetricCard);
    fixture.componentRef.setInput('label', 'Library');
    fixture.componentRef.setInput('value', '12');
    fixture.componentRef.setInput('loading', false);
    fixture.detectChanges();

    expect(fixtureHost(fixture).querySelector('.metric-card.mm-content-enter')).toBeNull();
    expect(fixtureHost(fixture).querySelector('.metric-card')).toBeTruthy();
  });
});
