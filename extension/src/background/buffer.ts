// storage.local-backed event buffer with a 50-entry cap and auto-flush.
import { eventsEndpoint } from "../shared/backend-endpoint";
import { newEventId } from "../shared/types";
import type { BehaviorEvent } from "../shared/types";

export const BUFFER_KEY = "talentforge_event_buffer";
export const BUFFER_CAP = 50;

interface StorageLocal {
  get(keys: string): Promise<{ [key: string]: unknown }>;
  set(items: Record<string, unknown>): Promise<void>;
  remove(keys: string): Promise<void>;
}

function getStorageLocal(): StorageLocal | null {
  try {
    const chromeApi = (
      globalThis as { chrome?: { storage?: { local?: StorageLocal } } }
    ).chrome;
    return chromeApi?.storage?.local ?? null;
  } catch {
    return null;
  }
}

async function readEvents(): Promise<BehaviorEvent[]> {
  const storage = getStorageLocal();
  if (!storage) return [];
  try {
    const items = await storage.get(BUFFER_KEY);
    const raw = items[BUFFER_KEY];
    return Array.isArray(raw) ? (raw as BehaviorEvent[]) : [];
  } catch {
    return [];
  }
}

async function writeEvents(events: BehaviorEvent[]): Promise<void> {
  const storage = getStorageLocal();
  if (!storage) return;
  await storage.set({ [BUFFER_KEY]: events });
}

async function removeBufferKey(): Promise<void> {
  const storage = getStorageLocal();
  if (!storage) return;
  try {
    await storage.remove(BUFFER_KEY);
  } catch {
    // Best-effort; an undeleted batch only costs a deduplicated redelivery.
  }
}

// Serialize storage read-modify-write cycles so concurrent message handlers
// (and an alarm flush) can't interleave reads and lose events.
let mutationTail: Promise<void> = Promise.resolve();

function withMutation<T>(mutation: () => Promise<T>): Promise<T> {
  const run = mutationTail.then(mutation, mutation);
  mutationTail = run.then(
    () => undefined,
    () => undefined,
  );
  return run;
}

export function ensureEventId(event: BehaviorEvent): BehaviorEvent {
  const existing = typeof event.event_id === "string" ? event.event_id.trim() : "";
  if (existing) return event;
  return { ...event, event_id: newEventId() };
}

/**
 * Append an event to the persistent buffer (capped at BUFFER_CAP; oldest events
 * are evicted past the cap). Resolves true when the buffer is full, so the
 * caller knows a flush is warranted.
 */
export function enqueueEvent(event: BehaviorEvent): Promise<boolean> {
  return withMutation(async () => {
    const events = await readEvents();
    events.push(ensureEventId(event));
    if (events.length > BUFFER_CAP) events.shift();
    await writeEvents(events);
    return events.length >= BUFFER_CAP;
  });
}

/**
 * Read a snapshot of the buffered events; storage is left intact. Events are
 * removed only after a successful POST (by event_id, inside flushBuffer), so
 * an MV3 service-worker kill mid-flush costs at most a redelivery — which the
 * backend's event_id idempotency deduplicates (at-least-once delivery).
 * The snapshot is a defensive copy: later enqueues must not leak into a
 * batch that was already claimed (or its flush would remove them).
 */
export function claimBuffer(): Promise<BehaviorEvent[]> {
  return withMutation(async () => {
    const events = await readEvents();
    return [...events];
  });
}

/**
 * POST a batch to the backend. On success the flushed events are removed from
 * storage by event_id (events enqueued in the meantime are preserved; an
 * emptied buffer removes the key entirely); on failure storage is left
 * untouched so the next alarm retries the batch.
 */
export function flushBuffer(events: BehaviorEvent[]): Promise<void> {
  if (events.length === 0) return Promise.resolve();
  return (async () => {
    try {
      const response = await fetch(eventsEndpoint(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events }),
      });
      if (!response.ok) return;
      const flushedIds = new Set(events.map((event) => event.event_id));
      await withMutation(async () => {
        const current = await readEvents();
        const remaining = current.filter((event) => !flushedIds.has(event.event_id));
        if (remaining.length === 0) {
          await removeBufferKey();
        } else {
          await writeEvents(remaining);
        }
      });
    } catch {
      // Network or storage failure — the batch stays durable for the next alarm.
    }
  })();
}

/** Test-only: reset the serialization tail between tests. */
export function __resetBufferForTests(): void {
  mutationTail = Promise.resolve();
}
