import { ChangeDetectionStrategy, Component, computed, ElementRef, input, model, viewChildren } from '@angular/core';

export interface MmSegmentedOption<T extends string = string> {
  value: T;
  label: string;
}

@Component({
  selector: 'mm-segmented-control',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="mm-segmented"
      [class.mm-segmented--sm]="size() === 'sm'"
      [class.mm-segmented--md]="size() === 'md'"
      role="radiogroup"
      [attr.aria-label]="label()"
    >
      @for (option of options(); track option.value; let index = $index) {
        <button
          #optionButton
          type="button"
          role="radio"
          class="mm-segmented__option"
          [class.is-active]="value() === option.value"
          [attr.aria-checked]="value() === option.value"
          [tabIndex]="selectedIndex() === index ? 0 : -1"
          (click)="select(option.value)"
          (keydown)="onKeydown($event, index)"
        >{{ option.label }}</button>
      }
    </div>
  `,
  styles: `
    :host { display: inline-block; min-width: 0; }
    .mm-segmented {
      display: inline-flex;
      max-width: 100%;
      gap: 3px;
      padding: 3px;
      overflow-x: auto;
      border: 1px solid var(--mm-component-border);
      border-radius: var(--mm-radius-md);
      background: var(--mm-component-card-bg);
      scrollbar-width: none;
    }
    .mm-segmented::-webkit-scrollbar { display: none; }
    .mm-segmented__option {
      flex: none;
      border: 1px solid transparent;
      border-radius: var(--mm-radius-sm);
      background: transparent;
      color: var(--mm-component-control-text);
      cursor: pointer;
      font: 700 var(--mm-text-sm)/1 var(--mm-font-body);
      white-space: nowrap;
    }
    .mm-segmented--sm .mm-segmented__option { padding: 6px 10px; font-size: var(--mm-text-sm); }
    .mm-segmented--md .mm-segmented__option { padding: 8px 12px; font-size: 14px; }
    .mm-segmented__option:hover,
    .mm-segmented__option.is-active { background: var(--mm-component-control-pressed-bg); color: var(--mm-component-control-pressed-text); }
    .mm-segmented__option:focus-visible { outline: 3px solid var(--mm-component-focus-ring); outline-offset: 2px; }
  `,
})
export class MmSegmentedControl<T extends string = string> {
  readonly options = input.required<MmSegmentedOption<T>[]>();
  readonly value = model.required<T>();
  readonly label = input.required<string>();
  readonly size = input<'sm' | 'md'>('md');
  private readonly buttons = viewChildren<ElementRef<HTMLButtonElement>>('optionButton');

  readonly selectedIndex = computed(() => {
    const index = this.options().findIndex((option) => option.value === this.value());
    return index >= 0 ? index : 0;
  });

  select(value: T): void {
    this.value.set(value);
  }

  onKeydown(event: KeyboardEvent, index: number): void {
    const options = this.options();
    if (!options.length) return;
    let nextIndex = index;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') nextIndex = (index + 1) % options.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') nextIndex = (index - 1 + options.length) % options.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = options.length - 1;
    else return;
    event.preventDefault();
    this.value.set(options[nextIndex].value);
    queueMicrotask(() => {
      this.buttons()[nextIndex]?.nativeElement.focus();
    });
  }
}
