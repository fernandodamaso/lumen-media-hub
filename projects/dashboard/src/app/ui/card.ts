import { AfterViewChecked, ChangeDetectionStrategy, Component, ElementRef, inject, input } from '@angular/core';

@Component({
  selector: 'mm-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './card.html',
  styleUrl: './card.scss',
})
export class MmCard implements AfterViewChecked {
  readonly labelledBy = input('');
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  ngAfterViewChecked(): void {
    this.setRegionVisibility('.mm-card__header');
    this.setRegionVisibility('.mm-card__footer');
  }

  private setRegionVisibility(regionSelector: string): void {
    const region = this.host.nativeElement.querySelector<HTMLElement>(regionSelector);
    if (!region) return;
    const isEmpty = !region.querySelector(':scope > div > *');
    region.toggleAttribute('hidden', isEmpty);
    region.style.display = isEmpty ? 'none' : '';
  }
}
