import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmButton, MmIconButton, MmMediaCard, MmProgress, MmStateCard, MmStatus, MmTooltip } from './index';

describe('app/ui primitives', () => {
  it('renders button content and preserves its base and variant classes', () => {
    const fixture = TestBed.createComponent(MmButton);
    fixture.componentRef.setInput('variant', 'quiet');
    fixture.componentRef.setInput('busy', true);
    fixture.detectChanges();
    const button = fixtureHost(fixture).querySelector('button');

    expect(button?.className).toContain('mm-button');
    expect(button?.className).toContain('mm-button--quiet');
    expect(button?.querySelector('.mm-button__spinner')).toBeTruthy();
    expect(button?.getAttribute('aria-busy')).toBe('true');
  });

  it('keeps quiet and danger buttons on the shared pill radius', () => {
    const quiet = TestBed.createComponent(MmButton);
    quiet.componentRef.setInput('variant', 'quiet');
    quiet.componentRef.setInput('label', 'Cancel');
    quiet.detectChanges();
    const danger = TestBed.createComponent(MmButton);
    danger.componentRef.setInput('variant', 'danger');
    danger.componentRef.setInput('label', 'Delete media');
    danger.detectChanges();
    expect(getComputedStyle(fixtureHost(quiet).querySelector('button') as Element).borderRadius).toBe(
      getComputedStyle(fixtureHost(danger).querySelector('button') as Element).borderRadius,
    );
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

  it('exposes the gold and ghost button variants', () => {
    const gold = TestBed.createComponent(MmButton);
    gold.componentRef.setInput('variant', 'gold');
    gold.componentRef.setInput('label', 'Add media');
    gold.detectChanges();
    const goldButton = fixtureHost(gold).querySelector('button');
    expect(goldButton?.className).toContain('mm-button--gold');
    expect(goldButton?.textContent).toContain('Add media');

    const ghost = TestBed.createComponent(MmButton);
    ghost.componentRef.setInput('variant', 'ghost');
    ghost.componentRef.setInput('label', 'Details');
    ghost.detectChanges();
    const ghostButton = fixtureHost(ghost).querySelector('button');
    expect(ghostButton?.className).toContain('mm-button--ghost');
    expect(ghostButton?.textContent).toContain('Details');
  });

  it('defines gold and ghost variant styles', () => {
    const fixture = TestBed.createComponent(MmButton);
    fixture.detectChanges();
    const css = Array.from(document.head.querySelectorAll('style'))
      .map((style) => style.textContent)
      .join('\n');
    expect(css).toContain('mm-button--gold');
    expect(css).toContain('mm-button--ghost');
  });

  it('applies button size modifiers', () => {
    const sm = TestBed.createComponent(MmButton);
    sm.componentRef.setInput('size', 'sm');
    sm.detectChanges();
    expect(fixtureHost(sm).querySelector('button')?.className).toContain('mm-button--sm');

    const lg = TestBed.createComponent(MmButton);
    lg.componentRef.setInput('size', 'lg');
    lg.detectChanges();
    expect(fixtureHost(lg).querySelector('button')?.className).toContain('mm-button--lg');
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

  it('renders media cards as a neutral wrapper without an article root', () => {
    const fixture = TestBed.createComponent(MmMediaCard);
    fixture.detectChanges();
    const host = fixtureHost(fixture);

    expect(host.querySelector('article')).toBeNull();
    expect(host.querySelector('.mm-media-card')?.tagName).toBe('DIV');
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

  it('exposes aria-pressed on toggle icon buttons', () => {
    const fixture = TestBed.createComponent(MmIconButton);
    fixture.componentRef.setInput('label', 'Liked');
    fixture.componentRef.setInput('toggle', true);
    fixture.componentRef.setInput('pressed', true);
    fixture.detectChanges();
    const button = fixtureHost(fixture).querySelector('button');

    expect(button?.getAttribute('aria-pressed')).toBe('true');
    expect(button?.classList.contains('mm-icon-button--pressed')).toBe(true);

    fixture.componentRef.setInput('pressed', false);
    fixture.detectChanges();
    expect(button?.getAttribute('aria-pressed')).toBe('false');
    expect(button?.classList.contains('mm-icon-button--pressed')).toBe(false);
  });

  it('omits aria-pressed when the icon button is not a toggle', () => {
    const fixture = TestBed.createComponent(MmIconButton);
    fixture.componentRef.setInput('label', 'Refresh');
    fixture.componentRef.setInput('pressed', true);
    fixture.detectChanges();
    const button = fixtureHost(fixture).querySelector('button');

    expect(button?.getAttribute('aria-pressed')).toBeNull();
  });

  it('exposes optional expanded state and controlled target', () => {
    const fixture = TestBed.createComponent(MmIconButton);
    fixture.componentRef.setInput('label', 'Hide activity rail');
    fixture.componentRef.setInput('expanded', true);
    fixture.componentRef.setInput('ariaControls', 'activity-rail');
    fixture.detectChanges();
    const button = fixtureHost(fixture).querySelector('button');

    expect(button?.getAttribute('aria-expanded')).toBe('true');
    expect(button?.getAttribute('aria-controls')).toBe('activity-rail');
  });

  it('applies the danger tone modifier', () => {
    const fixture = TestBed.createComponent(MmIconButton);
    fixture.componentRef.setInput('label', 'Delete');
    fixture.componentRef.setInput('tone', 'danger');
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('button')?.classList.contains('mm-icon-button--danger')).toBe(
      true,
    );

    const plain = TestBed.createComponent(MmIconButton);
    plain.componentRef.setInput('label', 'Refresh');
    plain.detectChanges();
    expect(fixtureHost(plain).querySelector('button')?.classList.contains('mm-icon-button--danger')).toBe(
      false,
    );
  });

  it('applies the overlay surface modifier', () => {
    const fixture = TestBed.createComponent(MmIconButton);
    fixture.componentRef.setInput('label', 'Mark watched');
    fixture.componentRef.setInput('surface', 'overlay');
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('button')?.classList.contains('mm-icon-button--overlay')).toBe(
      true,
    );
  });

  it('renders as an external link when href is set', () => {
    const fixture = TestBed.createComponent(MmIconButton);
    fixture.componentRef.setInput('label', 'Play Dune');
    fixture.componentRef.setInput('href', 'https://jf.example/dune');
    fixture.componentRef.setInput('surface', 'overlay');
    fixture.detectChanges();
    const link = fixtureHost(fixture).querySelector('a.mm-icon-button--overlay') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('https://jf.example/dune');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noreferrer');
    expect(link.getAttribute('aria-label')).toBe('Play Dune');
    expect(fixtureHost(fixture).querySelector('button')).toBeNull();
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
