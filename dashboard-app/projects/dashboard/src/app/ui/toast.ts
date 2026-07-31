import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MmToastService } from './toast.service';

@Component({
  selector: 'mm-toast-host',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="mm-toast-host" aria-live="polite" aria-relevant="additions">
      @for (toast of toasts.messages(); track toast.id) {
        <div
          class="mm-toast mm-toast--{{ toast.tone }}"
          [class.mm-toast--hide]="toast.hidden"
          role="status"
        >
          <div class="mm-toast__title">{{ toast.title }}</div>
          @if (toast.body) {
            <div class="mm-toast__body">{{ toast.body }}</div>
          }
          <button type="button" class="mm-toast__close" (click)="toasts.dismiss(toast.id)">×</button>
        </div>
      }
    </div>
  `,
  styleUrl: './toast.scss',
})
export class MmToastHost {
  readonly toasts = inject(MmToastService);
}

@Component({
  selector: 'mm-toast',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div class="mm-toast mm-toast--gold" role="status"><ng-content /></div>`,
  styleUrl: './toast.scss',
})
export class MmToast {}
