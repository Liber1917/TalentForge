// storage.local-backed event buffer with a 50-entry cap and auto-flush (Task 4 fills implementation).
export const BUFFER_KEY = "talentforge_event_buffer";
export const BUFFER_CAP = 50;

export function enqueue(_event: unknown): Promise<void> {
  return Promise.resolve();
}

export function flushBuffer(): Promise<void> {
  return Promise.resolve();
}
