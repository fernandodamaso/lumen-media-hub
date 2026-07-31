import { ChangeDetectionStrategy, Component, computed, input, model } from '@angular/core';

// ponytail: default aria-label removes the need for a visible label in every demo/story.

@Component({
  selector: 'mm-slider',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="mm-slider">
      <input
        type="range"
        class="mm-slider__input"
        [min]="min()"
        [max]="max()"
        [step]="step()"
        [disabled]="disabled()"
        [value]="value()"
        [style.--fill]="fillPercent() + '%'"
        (input)="onInput($event)"
        [attr.aria-label]="ariaLabel()"
        [attr.aria-valuenow]="value()"
        [attr.aria-valuemin]="min()"
        [attr.aria-valuemax]="max()"
      />
      @if (showValue()) {
        <span class="mm-slider__value">{{ value() }}</span>
      }
    </div>
  `,
  styleUrl: './slider.scss',
})
export class MmSlider {
  readonly min = input(0);
  readonly max = input(100);
  readonly step = input(1);
  readonly disabled = input(false);
  readonly showValue = input(true);
  readonly ariaLabel = input('Slider');
  readonly value = model(42);
  readonly fillPercent = computed(() => {
    const span = this.max() - this.min();
    if (span <= 0) return 0;
    return ((this.value() - this.min()) / span) * 100;
  });

  onInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.value.set(Number(input.value));
  }
}
