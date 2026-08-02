import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmInput } from './input';

describe('MmInput', () => {
  it('renders a labeled field', () => {
    const fixture = TestBed.createComponent(MmInput);
    fixture.componentRef.setInput('label', 'Email');
    fixture.componentRef.setInput('placeholder', 'you@cinema.tv');
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('Email');
    expect(fixtureHost(fixture).querySelector('input')).toBeTruthy();
  });

  it('renders native search semantics and the supplied id and accessible name', () => {
    const fixture = TestBed.createComponent(MmInput);
    fixture.componentRef.setInput('type', 'search');
    fixture.componentRef.setInput('inputId', 'media-search');
    fixture.componentRef.setInput('ariaLabel', 'Search media');
    fixture.detectChanges();
    const input = fixtureHost(fixture).querySelector('input');
    expect(input?.type).toBe('search');
    expect(input?.id).toBe('media-search');
    expect(input?.getAttribute('aria-label')).toBe('Search media');
  });
});
