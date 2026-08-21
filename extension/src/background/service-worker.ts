// Background service worker: receives BEHAVIOR_EVENT → buffer → periodic flush to backend (Task 4 fills implementation).
import { enqueue, flushBuffer } from "./buffer";

export function initServiceWorker(): void {
  void enqueue;
  void flushBuffer;
  // Task 4: chrome.runtime.onMessage routing + 30s alarm flush.
}

(globalThis as Record<string, unknown>).__talentforge_sw = true;
