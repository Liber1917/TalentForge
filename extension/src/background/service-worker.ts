// Background service worker: receives BEHAVIOR_EVENT → buffer → periodic flush to backend.
// On Firefox the same bundle runs as an event page (background.scripts) — the
// chrome.* namespace is an alias of browser.* there, so promise usage works.
import { claimBuffer, enqueueEvent, flushBuffer } from "./buffer";
import { backendEndpoint } from "../shared/backend-endpoint";
import { clampAlarmPeriodForFirefox } from "../shared/firefox";
import { initTaskRunner } from "./task_runner";
import type { BehaviorEvent } from "../shared/types";

export const FLUSH_ALARM_NAME = "talentforge-flush";
export const FLUSH_PERIOD_MINUTES = 0.5;

// Firefox 暴露全局 browser 命名空间而 Chrome 没有（webextension-polyfill 的
// 同款判别法）——以此选择 alarm 周期，不依赖浏览器对 <1min 周期的隐式钳制。
export function isFirefoxRuntime(): boolean {
  const browserApi = (globalThis as { browser?: unknown }).browser;
  return typeof browserApi === "object" && browserApi !== null;
}

/** Firefox 会把 <1 分钟的 alarm 周期钳到 1 分钟；显式取有效值。 */
export function effectiveFlushPeriodMinutes(): number {
  return clampAlarmPeriodForFirefox(FLUSH_PERIOD_MINUTES, isFirefoxRuntime());
}

async function handleBehaviorEvent(event: BehaviorEvent): Promise<void> {
  const full = await enqueueEvent(event);
  if (full) {
    await flushBuffer(await claimBuffer());
  }
}

async function handleJobsBatch(source: string, jobs: unknown[]): Promise<void> {
  if (!Array.isArray(jobs) || jobs.length === 0) return;
  try {
    await fetch(`${backendEndpoint()}/jobs/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source, jobs }),
    });
  } catch {
    // Backend down — drop; the next harvest trigger re-sends (URL dedupe server-side).
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
      if (message?.action === "JOBS_BATCH") {
        void handleJobsBatch(String(message.source ?? ""), message.jobs)
          .then(() => {
            try {
              sendResponse?.({ ok: true });
            } catch {
              // The sender may have gone away after persistence.
            }
          })
          .catch(() => {
            try {
              sendResponse?.({ ok: false });
            } catch {
              // Nothing else to report.
            }
          });
        return true;
      }
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
      periodInMinutes: effectiveFlushPeriodMinutes(),
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
initTaskRunner();
