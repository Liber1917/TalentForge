import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BUFFER_CAP,
  BUFFER_KEY,
  __resetBufferForTests,
} from "../background/buffer";
import {
  FLUSH_ALARM_NAME,
  FLUSH_PERIOD_MINUTES,
  effectiveFlushPeriodMinutes,
  initServiceWorker,
} from "../background/service-worker";
import { FIREFOX_MIN_ALARM_PERIOD_MINUTES } from "../shared/firefox";
import type { BehaviorEvent } from "../shared/types";

function makeEvent(id: string): BehaviorEvent {
  return {
    event_id: id,
    type: "click",
    url: "https://www.zhihu.com/question/42",
    title: "Some question",
    timestamp: new Date().toISOString(),
    source_platform: "zhihu",
    context: {
      pageType: "question",
      viewport: { width: 1280, height: 720 },
      scrollPosition: { x: 0, y: 0 },
    },
    metadata: {},
  };
}

type MessageListener = (
  message: unknown,
  sender: unknown,
  sendResponse: (response?: unknown) => void,
) => unknown;

function installChromeMock(): {
  store: Record<string, unknown>;
  listeners: MessageListener[];
  alarmListeners: Array<(alarm: unknown) => void>;
  createAlarm: ReturnType<typeof vi.fn>;
} {
  const store: Record<string, unknown> = {};
  const listeners: MessageListener[] = [];
  const alarmListeners: Array<(alarm: unknown) => void> = [];
  const createAlarm = vi.fn();
  const local = {
    get: vi.fn(async (keys: string) => ({ [keys]: store[keys] })),
    set: vi.fn(async (items: Record<string, unknown>) => {
      Object.assign(store, items);
    }),
    remove: vi.fn(async (keys: string) => {
      delete store[keys];
    }),
  };
  const chromeMock = {
    runtime: {
      onMessage: {
        addListener: vi.fn((listener: MessageListener) => {
          listeners.push(listener);
        }),
      },
    },
    alarms: {
      create: createAlarm,
      onAlarm: {
        addListener: vi.fn((listener: (alarm: unknown) => void) => {
          alarmListeners.push(listener);
        }),
      },
    },
    storage: { local },
  };
  vi.stubGlobal("chrome", chromeMock as unknown as typeof chrome);
  return { store, listeners, alarmListeners, createAlarm };
}

describe("service-worker", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    __resetBufferForTests();
  });

  it("registers the flush alarm on init", () => {
    const { createAlarm } = installChromeMock();
    initServiceWorker();
    expect(createAlarm).toHaveBeenCalledWith(FLUSH_ALARM_NAME, {
      periodInMinutes: FLUSH_PERIOD_MINUTES,
    });
  });

  it("clamps the flush alarm period to 1 minute when the browser global is present (Firefox)", () => {
    const { createAlarm } = installChromeMock();
    vi.stubGlobal("browser", {}); // Firefox 暴露全局 browser 命名空间，Chrome 没有
    expect(effectiveFlushPeriodMinutes()).toBe(FIREFOX_MIN_ALARM_PERIOD_MINUTES);
    initServiceWorker();
    expect(createAlarm).toHaveBeenCalledWith(FLUSH_ALARM_NAME, {
      periodInMinutes: FIREFOX_MIN_ALARM_PERIOD_MINUTES,
    });
  });

  it("enqueues BEHAVIOR_EVENT messages into the buffer", async () => {
    const { store, listeners } = installChromeMock();
    initServiceWorker();
    const sendResponse = vi.fn();
    listeners[0]({ action: "BEHAVIOR_EVENT", data: makeEvent("e-1") }, null, sendResponse);
    await vi.waitFor(() => {
      const stored = store[BUFFER_KEY] as BehaviorEvent[] | undefined;
      expect(stored?.map((event) => event.event_id)).toEqual(["e-1"]);
    });
    expect(sendResponse).toHaveBeenCalledWith({ ok: true });
  });

  it("ignores non-BEHAVIOR_EVENT messages", async () => {
    const { store, listeners } = installChromeMock();
    initServiceWorker();
    const sendResponse = vi.fn();
    listeners[0]({ action: "SOMETHING_ELSE" }, null, sendResponse);
    expect(store[BUFFER_KEY]).toBeUndefined();
    expect(sendResponse).not.toHaveBeenCalled();
  });

  it("flushes immediately when the buffer reaches the cap", async () => {
    const { listeners } = installChromeMock();
    const fetchMock = vi.fn(async (_input: unknown, _init?: RequestInit) => ({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    initServiceWorker();
    for (let i = 0; i < BUFFER_CAP; i++) {
      listeners[0]({ action: "BEHAVIOR_EVENT", data: makeEvent(`e-${i}`) }, null, () => {});
    }
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = JSON.parse(String(fetchMock.mock.calls[0]![1]!.body));
    expect(body.events).toHaveLength(BUFFER_CAP);
  });

  it("relays JOBS_BATCH messages to the backend /api/jobs/batch", async () => {
    const { listeners } = installChromeMock();
    const fetchMock = vi.fn(async (_input: unknown, _init?: RequestInit) => ({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    initServiceWorker();
    const sendResponse = vi.fn();
    const card = { title: "T", company: "C", location: "L", salary: "1-2/天", url: "https://u", tags: [], description: "" };
    listeners[0]({ action: "JOBS_BATCH", source: "shixiseng", jobs: [card] }, null, sendResponse);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toContain("/api/jobs/batch");
    const body = JSON.parse(String(init!.body));
    expect(body.source).toBe("shixiseng");
    expect(body.jobs).toHaveLength(1);
    await vi.waitFor(() => expect(sendResponse).toHaveBeenCalledWith({ ok: true }));
  });

  it("ignores malformed JOBS_BATCH payloads", async () => {
    const { listeners } = installChromeMock();
    const fetchMock = vi.fn(async () => ({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    initServiceWorker();
    listeners[0]({ action: "JOBS_BATCH", source: "x", jobs: "not-a-list" }, null, () => {});
    await new Promise((r) => setTimeout(r, 20));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("flushes the buffer when the flush alarm fires", async () => {
    const { store, listeners, alarmListeners } = installChromeMock();
    const fetchMock = vi.fn(async (_input: unknown, _init?: RequestInit) => ({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    initServiceWorker();
    listeners[0]({ action: "BEHAVIOR_EVENT", data: makeEvent("e-1") }, null, () => {});
    await vi.waitFor(() => {
      expect((store[BUFFER_KEY] as BehaviorEvent[] | undefined)?.length).toBe(1);
    });
    alarmListeners[0]({ name: FLUSH_ALARM_NAME });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = JSON.parse(String(fetchMock.mock.calls[0]![1]!.body));
    expect(body.events.map((event: BehaviorEvent) => event.event_id)).toEqual(["e-1"]);
  });
});
