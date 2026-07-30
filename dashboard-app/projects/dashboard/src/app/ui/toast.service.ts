import { Injectable, signal } from '@angular/core';

export type MmToastTone = 'gold' | 'success' | 'error';

export interface MmToastMessage {
  id: string;
  title: string;
  body?: string;
  tone: MmToastTone;
}

@Injectable({ providedIn: 'root' })
export class MmToastService {
  private seq = 0;
  readonly messages = signal<MmToastMessage[]>([]);

  show(title: string, options: { body?: string; tone?: MmToastTone; durationMs?: number } = {}): void {
    const id = `toast-${++this.seq}`;
    const message: MmToastMessage = {
      id,
      title,
      body: options.body,
      tone: options.tone ?? 'gold',
    };
    this.messages.update((list) => [...list, message]);
    const duration = options.durationMs ?? 4200;
    window.setTimeout(() => {
      this.dismiss(id);
    }, duration);
  }

  dismiss(id: string): void {
    this.messages.update((list) => list.filter((item) => item.id !== id));
  }
}
