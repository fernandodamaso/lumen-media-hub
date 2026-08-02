const dialogPrototype = HTMLDialogElement.prototype as unknown as Record<string, unknown>;

if (typeof dialogPrototype['showModal'] !== 'function') {
  Object.defineProperty(dialogPrototype, 'showModal', {
    configurable: true,
    writable: true,
    value(this: HTMLDialogElement) {
      this.open = true;
    },
  });
}

if (typeof dialogPrototype['close'] !== 'function') {
  Object.defineProperty(dialogPrototype, 'close', {
    configurable: true,
    writable: true,
    value(this: HTMLDialogElement) {
      this.open = false;
      this.dispatchEvent(new Event('close'));
    },
  });
}
