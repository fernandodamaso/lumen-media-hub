import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { LucideSearch } from '@lucide/angular';

export type MmInputKind = 'text' | 'textarea' | 'search-pill';

@Component({
  selector: 'mm-input',
  imports: [LucideSearch],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `@switch (kind()) {
    @case ('search-pill') {
      <button type="button" class="mm-input mm-input--search-pill" [attr.data-testid]="testId()" [attr.aria-label]="ariaLabel() || placeholder()" [disabled]="disabled()" (click)="activated.emit()">
        <svg lucideSearch [size]="14" aria-hidden="true"></svg>
        <span class="mm-input__placeholder">{{ placeholder() }}</span>
        @if (shortcutLabel()) { <kbd>{{ shortcutLabel() }}</kbd> }
      </button>
    }
    @case ('textarea') {
      <label class="mm-input mm-input--textarea">
        @if (label()) { <span class="mm-input__label">{{ label() }}</span> }
        <textarea
          [id]="inputId() || null"
          [rows]="rows()"
          [placeholder]="placeholder()"
          [disabled]="disabled()"
          [attr.aria-label]="ariaLabel() || null"
          [value]="value()"
          (input)="valueChange.emit($any($event.target).value)"
        ></textarea>
      </label>
    }
    @default {
      <label class="mm-input mm-input--text">
        @if (label()) { <span class="mm-input__label">{{ label() }}</span> }
        <input
          [id]="inputId() || null"
          [type]="type()"
          [placeholder]="placeholder()"
          [disabled]="disabled()"
          [attr.aria-label]="ariaLabel() || null"
          [value]="value()"
          (input)="valueChange.emit($any($event.target).value)"
        />
      </label>
    }
  }`,
  styleUrl: './input.scss',
})
export class MmInput {
  readonly kind = input<MmInputKind>('text');
  readonly label = input('');
  readonly placeholder = input('');
  readonly value = input('');
  readonly disabled = input(false);
  readonly type = input<'text' | 'email' | 'password' | 'search'>('text');
  readonly inputId = input('');
  readonly ariaLabel = input('');
  readonly rows = input(3);
  readonly shortcutLabel = input('');
  readonly testId = input('mm-input');
  readonly valueChange = output<string>();
  readonly activated = output();
}
