import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom lacks the layout APIs Radix and Recharts probe; give them inert stand-ins.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = function scrollIntoView(): void {};
Element.prototype.hasPointerCapture = function hasPointerCapture(): boolean {
  return false;
};
Element.prototype.releasePointerCapture = function releasePointerCapture(): void {};

afterEach(() => {
  cleanup();
});
