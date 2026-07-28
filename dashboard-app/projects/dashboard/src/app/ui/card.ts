import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'mm-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './card.html',
  styleUrl: './card.scss',
})
export class MmCard {
  readonly labelledBy = input('');
}
