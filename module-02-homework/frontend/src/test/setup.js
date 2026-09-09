import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
// jsdom does not implement native dialog methods or modal focus behavior.
HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '');
  this.querySelector('[autofocus], input, button')?.focus();
};
HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
