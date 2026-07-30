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
});
