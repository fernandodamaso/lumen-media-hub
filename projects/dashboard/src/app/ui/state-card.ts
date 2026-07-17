import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { LucideAlertCircle, LucideInbox, LucideLoaderCircle } from '@lucide/angular';

export type MmStateCardKind = 'loading' | 'empty' | 'error';

@Component({
  selector: 'mm-state-card',
  imports: [LucideLoaderCircle, LucideInbox, LucideAlertCircle],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './state-card.html',
  styleUrl: './state-card.scss',
})
export class MmStateCard {
  readonly kind = input<MmStateCardKind>('empty');
  readonly title = input('Nothing here yet');
  readonly message = input('There is no content to show right now.');
  readonly tone = input<'default' | 'danger'>('default');
}
