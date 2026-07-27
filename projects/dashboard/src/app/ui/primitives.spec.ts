import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { MmButton, MmCard, MmIconButton, MmPoster, MmProgress, MmStateCard, MmStatus, MmThemePicker, MmTooltip } from './index';

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
    <h2 mm-card-header>Heading only</h2>
    <p>Card body</p>
  </mm-card>`,
})
class HeadingOnlyCardHost {}

@Component({
  standalone: true,
  imports: [MmCard],
  template: `<mm-card>
    <button mm-card-header-actions type="button">Only actions</button>
    <p>Card body</p>
  </mm-card>`,
})
class HeaderActionsOnlyCardHost {}

@Component({
  standalone: true,
  imports: [MmCard],
  template: `<mm-card>
    <p>Card body</p>
    <span mm-card-footer>Footer only</span>
  </mm-card>`,
})
class FooterContentOnlyCardHost {}

@Component({
  standalone: true,
  imports: [MmCard],
  template: `<mm-card>
    <p>Card body</p>
    <a mm-card-footer-actions href="/library">Footer actions</a>
  </mm-card>`,
})
class FooterActionsOnlyCardHost {}

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
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders button content and preserves its base and variant classes', () => {
    const fixture = TestBed.createComponent(MmButton);
    fixture.componentRef.setInput('variant', 'quiet');
    fixture.componentRef.setInput('busy', true);
    fixture.detectChanges();
    const button = fixtureHost(fixture).querySelector('button');

    expect(button?.className).toContain('mm-button');
    expect(button?.className).toContain('mm-button--quiet');
    expect(button?.getAttribute('aria-busy')).toBe('true');
  });

  it('does not transition button text color (avoids load-time ink flash)', () => {
    const fixture = TestBed.createComponent(MmButton);
    fixture.detectChanges();
    const css = Array.from(document.head.querySelectorAll('style'))
      .map((style) => style.textContent)
      .join('\n');
    expect(css).toMatch(/\.mm-button[^{]*\{[^}]*transition:[^}]*\}/);
    const transitionBlock = (/\.mm-button(?:\[_[^\]]*\])?\s*\{[^}]*transition:[^}]+\}/).exec(css)?.[0] ?? '';
    expect(transitionBlock).not.toMatch(/transition:[^;]*\bcolor\b/);
    expect(css).toContain('mm-button--primary');
  });

  it('exposes the danger button variant for error actions', () => {
    const fixture = TestBed.createComponent(MmButton);
    fixture.componentRef.setInput('variant', 'danger');
    fixture.componentRef.setInput('label', 'View issues');
    fixture.detectChanges();
    const button = fixtureHost(fixture).querySelector('button');

    expect(button?.className).toContain('mm-button--danger');
    expect(button?.textContent).toContain('View issues');
  });

  it('keeps the status base class alongside its tone class without a live region by default', () => {
    const fixture = TestBed.createComponent(MmStatus);
    fixture.componentRef.setInput('tone', 'danger');
    fixture.detectChanges();
    const status = fixtureHost(fixture).querySelector('.mm-status');

    expect(status?.classList).toContain('mm-status');
    expect(status?.classList).toContain('mm-status--danger');
    expect(status?.getAttribute('role')).toBeNull();
    expect(status?.getAttribute('aria-live')).toBeNull();
  });

  it('exposes an opt-in live region when announce is enabled', () => {
    const fixture = TestBed.createComponent(MmStatus);
    fixture.componentRef.setInput('tone', 'warning');
    fixture.componentRef.setInput('announce', true);
    fixture.detectChanges();
    const status = fixtureHost(fixture).querySelector('.mm-status');

    expect(status?.getAttribute('role')).toBe('status');
  });

  it('renders optional card regions and omits empty header and footer chrome without DOM mutation', () => {
    const complete = TestBed.createComponent(CardRegionsHost);
    complete.detectChanges();
    const completeRoot = fixtureHost(complete);
    expect(completeRoot.querySelector('.mm-card__header')?.textContent).toContain('Library');
    expect(completeRoot.querySelector('.mm-card__footer')?.textContent).toContain('8 items shown');
    expect(completeRoot.querySelector('.mm-card')?.getAttribute('aria-labelledby')).toBe('test-heading');
    expect(completeRoot.querySelector('.mm-card__header')?.hasAttribute('hidden')).toBe(false);
    expect(completeRoot.querySelector('.mm-card__footer')?.hasAttribute('hidden')).toBe(false);

    const bodyOnly = TestBed.createComponent(BodyOnlyCardHost);
    bodyOnly.detectChanges();
    const bodyOnlyRoot = fixtureHost(bodyOnly);
    expect(getComputedStyle(bodyOnlyRoot.querySelector('.mm-card__header') as Element).display).toBe('none');
    expect(getComputedStyle(bodyOnlyRoot.querySelector('.mm-card__footer') as Element).display).toBe('none');
    expect(bodyOnlyRoot.querySelector('.mm-card__header')?.hasAttribute('hidden')).toBe(false);

    const headingOnly = TestBed.createComponent(HeadingOnlyCardHost);
    headingOnly.detectChanges();
    const headingOnlyRoot = fixtureHost(headingOnly);
    expect(getComputedStyle(headingOnlyRoot.querySelector('.mm-card__header') as Element).display).not.toBe('none');
    expect(getComputedStyle(headingOnlyRoot.querySelector('.mm-card__footer') as Element).display).toBe('none');

    const headerActionsOnly = TestBed.createComponent(HeaderActionsOnlyCardHost);
    headerActionsOnly.detectChanges();
    const headerActionsOnlyRoot = fixtureHost(headerActionsOnly);
    expect(getComputedStyle(headerActionsOnlyRoot.querySelector('.mm-card__header') as Element).display).not.toBe(
      'none',
    );
    expect(headerActionsOnlyRoot.querySelector('.mm-card__actions')?.textContent).toContain('Only actions');

    const footerContentOnly = TestBed.createComponent(FooterContentOnlyCardHost);
    footerContentOnly.detectChanges();
    const footerContentOnlyRoot = fixtureHost(footerContentOnly);
    expect(getComputedStyle(footerContentOnlyRoot.querySelector('.mm-card__header') as Element).display).toBe('none');
    expect(getComputedStyle(footerContentOnlyRoot.querySelector('.mm-card__footer') as Element).display).not.toBe(
      'none',
    );

    const footerActionsOnly = TestBed.createComponent(FooterActionsOnlyCardHost);
    footerActionsOnly.detectChanges();
    const footerActionsOnlyRoot = fixtureHost(footerActionsOnly);
    expect(getComputedStyle(footerActionsOnlyRoot.querySelector('.mm-card__footer') as Element).display).not.toBe(
      'none',
    );
    expect(footerActionsOnlyRoot.querySelector('.mm-card__footer')?.textContent).toContain('Footer actions');

    const containerRegions = TestBed.createComponent(ContainerRegionsHost);
    containerRegions.detectChanges();
    const projectedFooter = fixtureHost(containerRegions).querySelector('.mm-card__footer') as HTMLElement;
    expect(projectedFooter.hidden).toBe(false);
    expect(projectedFooter.textContent).toContain('8 items shown');
    expect(projectedFooter.textContent).toContain('View all');
  });

  it('renders posters as a neutral wrapper without an article root', () => {
    const fixture = TestBed.createComponent(MmPoster);
    fixture.detectChanges();
    const host = fixtureHost(fixture);

    expect(host.querySelector('article')).toBeNull();
    expect(host.querySelector('.mm-poster')?.tagName).toBe('DIV');
  });

  it('clears the theme picker saved-state timeout on destroy', async () => {
    vi.useFakeTimers();
    try {
      const fixture = TestBed.createComponent(MmThemePicker);
      fixture.detectChanges();
      const picker = fixture.componentInstance;
      const tokyo = [...fixtureHost(fixture).querySelectorAll('button')].find((button) =>
        button.textContent.includes('Tokyo Night'),
      ) as HTMLButtonElement;

      tokyo.click();
      fixture.detectChanges();
      expect(picker.justSaved()).toBe(true);

      fixture.destroy();
      await vi.advanceTimersByTimeAsync(2000);
      expect(picker.justSaved()).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps shared buttons at least 40px high', () => {
    const fixture = TestBed.createComponent(MmButton);
    fixture.detectChanges();

    expect(getComputedStyle(fixtureHost(fixture).querySelector('button') as Element).minHeight).toBe('40px');
  });

  it('exposes progress semantics and the state-card danger tone', () => {
    const progress = TestBed.createComponent(MmProgress);
    progress.componentRef.setInput('value', 42);
    progress.detectChanges();
    const progressRoot = fixtureHost(progress);
    expect(progressRoot.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('42');
    expect(getComputedStyle(progressRoot).display).toBe('flex');

    const state = TestBed.createComponent(MmStateCard);
    state.componentRef.setInput('tone', 'danger');
    state.detectChanges();
    expect(fixtureHost(state).querySelector('.mm-state-card--danger')).toBeTruthy();
  });

  it('applies a centered layout modifier when centered is set', () => {
    const state = TestBed.createComponent(MmStateCard);
    state.componentRef.setInput('centered', true);
    state.detectChanges();
    expect(fixtureHost(state).querySelector('.mm-state-card--centered')).toBeTruthy();

    const plain = TestBed.createComponent(MmStateCard);
    plain.detectChanges();
    expect(fixtureHost(plain).querySelector('.mm-state-card--centered')).toBeNull();
  });

  it('normalizes progress values and applies tone classes', () => {
    const low = TestBed.createComponent(MmProgress);
    low.componentRef.setInput('value', -10);
    low.componentRef.setInput('tone', 'warning');
    low.detectChanges();
    const lowRoot = fixtureHost(low);
    expect(lowRoot.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('0');
    expect(lowRoot.querySelector('.mm-progress--warning')).toBeTruthy();

    const high = TestBed.createComponent(MmProgress);
    high.componentRef.setInput('value', 110);
    high.componentRef.setInput('tone', 'premiere');
    high.detectChanges();
    const highRoot = fixtureHost(high);
    expect(highRoot.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('100');
    expect(highRoot.querySelector('.mm-progress--premiere')).toBeTruthy();
  });

  it('disables the shimmer animation when the user prefers reduced motion', () => {
    const fixture = TestBed.createComponent(MmProgress);
    fixture.componentRef.setInput('live', true);
    fixture.detectChanges();
    const css = Array.from(document.head.querySelectorAll('style'))
      .map((style) => style.textContent)
      .join('\n');
    expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
    expect(css).toMatch(/\.mm-progress__bar--live(?:\[[^\]]*\])?::after\s*\{[^}]*animation\s*:\s*none/);
  });

  it('reflects the live input as a class modifier and preserves label rendering', () => {
    const live = TestBed.createComponent(MmProgress);
    live.componentRef.setInput('live', true);
    live.componentRef.setInput('value', 75);
    live.detectChanges();
    const liveRoot = fixtureHost(live);
    expect(liveRoot.querySelector('.mm-progress__bar--live')).toBeTruthy();
    expect(liveRoot.querySelector('.mm-progress__label')?.textContent).toContain('75');

    const plain = TestBed.createComponent(MmProgress);
    plain.componentRef.setInput('value', 30);
    plain.detectChanges();
    const plainRoot = fixtureHost(plain);
    expect(plainRoot.querySelector('.mm-progress__bar--live')).toBeNull();
    expect(plainRoot.querySelector('.mm-progress__label')?.textContent).toContain('30');
  });

  it('renders icon buttons with a required accessible label', () => {
    const fixture = TestBed.createComponent(MmIconButton);
    fixture.componentRef.setInput('label', 'Pause download');
    fixture.componentRef.setInput('busy', true);
    fixture.detectChanges();
    const button = fixtureHost(fixture).querySelector('button');

    expect(button?.getAttribute('aria-label')).toBe('Pause download');
    expect(button?.getAttribute('aria-busy')).toBe('true');
    expect(button?.disabled).toBe(true);
  });

  it('disables icon buttons when disabled without busy', () => {
    const fixture = TestBed.createComponent(MmIconButton);
    fixture.componentRef.setInput('label', 'Pause download');
    fixture.componentRef.setInput('disabled', true);
    fixture.componentRef.setInput('busy', false);
    fixture.detectChanges();
    const button = fixtureHost(fixture).querySelector('button');

    expect(button?.disabled).toBe(true);
    expect(button?.getAttribute('aria-busy')).toBeNull();
  });

  it('keeps the theme picker selection aligned with the applied theme', () => {
    const fixture = TestBed.createComponent(MmThemePicker);
    const picker = fixture.componentInstance;
    picker.themeService.setTheme('tokyo-night');
    fixture.detectChanges();
    const buttons = () => [...fixtureHost(fixture).querySelectorAll('button')];

    expect(document.documentElement.dataset['theme']).toBe('tokyo-night');
    expect(buttons().find((button) => button.textContent.includes('Tokyo Night'))?.classList.contains('is-active')).toBe(
      true,
    );

    picker.themeService.setTheme('github-dark-pro');
    fixture.detectChanges();
    expect(buttons().find((button) => button.textContent.includes('GitHub Dark'))?.classList.contains('is-active')).toBe(
      true,
    );
  });

  it('lets the primary button receive keyboard focus', () => {
    const fixture = TestBed.createComponent(MmButton);
    fixture.componentRef.setInput('label', 'Focus me');
    fixture.detectChanges();
    const button = fixtureHost(fixture).querySelector('button') as HTMLButtonElement;
    button.focus();
    expect(document.activeElement).toBe(button);
  });

  it('renders default and accent tooltips around a trigger', () => {
    @Component({
      standalone: true,
      imports: [MmTooltip],
      template: `
        <mm-tooltip text="Refresh">
          <button type="button">Refresh</button>
        </mm-tooltip>
        <mm-tooltip text="Play" tone="accent" placement="bottom">
          <button type="button">Play</button>
        </mm-tooltip>
      `,
    })
    class TooltipHost {}

    const fixture = TestBed.createComponent(TooltipHost);
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    const tips = root.querySelectorAll('mm-tooltip');

    expect(tips).toHaveLength(2);
    expect(tips[0].classList.contains('mm-tooltip--accent')).toBe(false);
    expect(tips[1].classList.contains('mm-tooltip--accent')).toBe(true);
    expect(tips[1].classList.contains('mm-tooltip--bottom')).toBe(true);
    expect(root.querySelectorAll('[role="tooltip"]')[0].textContent.trim()).toBe('Refresh');
    expect(root.querySelectorAll('[role="tooltip"]')[1].textContent.trim()).toBe('Play');
  });
});
