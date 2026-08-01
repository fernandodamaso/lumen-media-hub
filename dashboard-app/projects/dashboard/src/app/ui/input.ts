import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

export type MmInputKind = 'text' | 'textarea';

@Component({
  selector: 'mm-input',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `@switch (kind()) {
    @case ('textarea') {
      <label class="mm-input mm-input--textarea" [class.mm-input--error]="invalid()">
        @if (label()) { <span class="mm-input__label">{{ label() }}</span> }
        <textarea
          [rows]="rows()"
          [placeholder]="placeholder()"
          [disabled]="disabled()"
          [value]="value()"
          [attr.aria-label]="label() || ariaLabel() || null"
          [attr.aria-invalid]="invalid() || null"
          [attr.aria-describedby]="message() ? messageId() : null"
          (input)="valueChange.emit($any($event.target).value)"
        ></textarea>
        @if (message()) {
          <span class="mm-input__message" [class.mm-input__message--error]="invalid()" [id]="messageId()">
            {{ message() }}
          </span>
        }
      </label>
    }
    @default {
      <label class="mm-input mm-input--text" [class.mm-input--error]="invalid()">
        @if (label()) { <span class="mm-input__label">{{ label() }}</span> }
        <input
          [type]="type()"
          [placeholder]="placeholder()"
          [disabled]="disabled()"
          [value]="value()"
          [attr.aria-label]="label() || ariaLabel() || null"
          [attr.aria-invalid]="invalid() || null"
          [attr.aria-describedby]="message() ? messageId() : null"
          (input)="valueChange.emit($any($event.target).value)"
        />
        @if (message()) {
          <span class="mm-input__message" [class.mm-input__message--error]="invalid()" [id]="messageId()">
            {{ message() }}
          </span>
        }
      </label>
    }
  }`,
  styleUrl: './input.scss',
})
export class MmInput {
  readonly kind = input<MmInputKind>('text');
  readonly label = input('');
  readonly ariaLabel = input('');
  readonly placeholder = input('');
  readonly value = input('');
  readonly disabled = input(false);
  readonly invalid = input(false);
  readonly message = input('');
  readonly type = input<'text' | 'email' | 'password'>('text');
  readonly rows = input(3);
  readonly testId = input('mm-input');
  readonly valueChange = output<string>();

  readonly messageId = () => `${this.testId()}-message`;
}
