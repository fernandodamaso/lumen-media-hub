import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { fixtureHost } from '../../testing/fixture-host';
import { MmButtonLink } from './button-link';

describe('MmButtonLink', () => {
  it('reuses button classes for internal and external destinations', () => {
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
    const fixture = TestBed.createComponent(MmButtonLink);
    fixture.componentRef.setInput('destination', '/library');
    fixture.componentRef.setInput('label', 'Library');
    fixture.componentRef.setInput('variant', 'quiet');
    fixture.componentRef.setInput('size', 'sm');
    fixture.detectChanges();
    const link = fixtureHost(fixture).querySelector('a');
    expect(link?.className).toContain('mm-button--quiet');
    expect(link?.className).toContain('mm-button--sm');
    expect(link?.getAttribute('href')).toBe('/library');

    fixture.componentRef.setInput('mode', 'external');
    fixture.componentRef.setInput('destination', 'https://example.com');
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('a')?.getAttribute('target')).toBe('_blank');
  });
});
