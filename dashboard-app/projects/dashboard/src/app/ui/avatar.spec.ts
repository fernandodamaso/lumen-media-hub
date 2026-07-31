import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmAvatar } from './avatar';

describe('MmAvatar', () => {
  it('renders initials', () => {
    const fixture = TestBed.createComponent(MmAvatar);
    fixture.componentRef.setInput('initials', 'AB');
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('AB');
  });
});

describe('MmAvatar variants', () => {
  it('renders an image when src is set', () => {
    const fixture = TestBed.createComponent(MmAvatar);
    fixture.componentRef.setInput('src', 'data:image/svg+xml,x');
    fixture.componentRef.setInput('label', 'Fernanda');
    fixture.detectChanges();
    const img = fixtureHost(fixture).querySelector('img');
    expect(img).toBeTruthy();
  });

  it('falls back to initials when the image fails to load', () => {
    const fixture = TestBed.createComponent(MmAvatar);
    fixture.componentRef.setInput('src', 'https://invalid.example/x.png');
    fixture.componentRef.setInput('initials', 'FE');
    fixture.detectChanges();
    const img = fixtureHost(fixture).querySelector('img') as HTMLImageElement;
    img.dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('img')).toBeNull();
    expect(fixtureHost(fixture).textContent).toContain('FE');
  });

  it('renders an icon variant when icon is set', () => {
    const fixture = TestBed.createComponent(MmAvatar);
    fixture.componentRef.setInput('icon', 'user');
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('svg')).toBeTruthy();
  });
});
