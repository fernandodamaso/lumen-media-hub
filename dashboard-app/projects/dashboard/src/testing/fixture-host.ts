import { ComponentFixture } from '@angular/core/testing';

export function fixtureHost(fixture: ComponentFixture<unknown>): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}
