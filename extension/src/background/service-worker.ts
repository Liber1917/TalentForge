// Background service worker: receives BEHAVIOR_EVENT → buffer → periodic flush to backend.
import { claimBuffer, enqueueEvent, flushBuffer } from "./buffer";
import type { BehaviorEvent } from "../shared/types";

export const FLUSH_ALARM_NAME = "talentforge-flush";
export const FLUSH_PERIOD_MINUTES = 0.5;

async function handleBehaviorEvent(event: BehaviorEvent): Promise<void> {
  const full = await enqueueEvent(event);
  if (full) {
    await flushBuffer(await claimBuffer());
  }
}

/**
 * Wire up message routing and the periodic flush alarm. Guarded against a
 * missing chrome API so importing the module (e.g. in tests) is a no-op.
 */
export function initServiceWorker(): void {
  const chromeApi = (globalThis as { chrome?: typeof chrome }).chrome;
  if (!chromeApi) return;

  chromeApi.runtime?.onMessage?.addListener?.(
    (message, _sender, sendResponse) => {
      if (message?.action !== "BEHAVIOR_EVENT") return;
      void handleBehaviorEvent(message.data as BehaviorEvent)
        .then(() => {
          try {
            sendResponse?.({ ok: true });
          } catch {
            // The sender may have gone away after persistence.
          }
        })
        .catch((err) => {
          console.warn(
            "[TalentForge] Event enqueue failed:",
            err instanceof Error ? err.message : String(err),
          );
          try {
            sendResponse?.({ ok: false });
          } catch {
            // Nothing else to report.
          }
        });
      return true;
    },
  );

  if (chromeApi.alarms?.create) {
    chromeApi.alarms.create(FLUSH_ALARM_NAME, {
      periodInMinutes: FLUSH_PERIOD_MINUTES,
    });
  }

  chromeApi.alarms?.onAlarm?.addListener?.((alarm) => {
    if (alarm?.name !== FLUSH_ALARM_NAME) return;
    void (async () => {
      try {
        await flushBuffer(await claimBuffer());
      } catch (err) {
        console.warn(
          "[TalentForge] Alarm flush failed:",
          err instanceof Error ? err.message : String(err),
        );
      }
    })();
  });
}

initServiceWorker();
