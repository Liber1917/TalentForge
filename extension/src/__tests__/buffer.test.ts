import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BUFFER_CAP,
  BUFFER_KEY,
  __resetBufferForTests,
  claimBuffer,
  enqueueEvent,
  flushBuffer,
} from "../background/buffer";
import type { BehaviorEvent } from "../shared/types";

function makeEvent(id: string): BehaviorEvent {
  return {
    event_id: id,
    type: "click",
    url: "https://www.bilibili.com/video/BV1xx",
    title: "Some title",
    timestamp: new Date().toISOString(),
    source_platform: "bilibili",
    context: {
      pageType: "video",
      viewport: { width: 1280, height: 720 },
      scrollPosition: { x: 0, y: 0 },
    },
    metadata: {},
  };
}

function installChromeMock(): {
  store: Record<string, unknown>;
  local: {
    get: ReturnType<typeof vi.fn>;
    set: ReturnType<typeof vi.fn>;
    remove: ReturnType<typeof vi.fn>;
  };
} {
  const store: Record<string, unknown> = {};
  const local = {
    get: vi.fn(async (keys: string) => ({ [keys]: store[keys] })),
    set: vi.fn(async (items: Record<string, unknown>) => {
      Object.assign(store, items);
    }),
    remove: vi.fn(async (keys: string) => {
      delete store[keys];
    }),
  };
  vi.stubGlobal("chrome", { storage: { local } });
  return { store, local };
}

describe("buffer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    __resetBufferForTests();
  });

  it("enqueues events into storage.local and reports full at the cap", async () => {
    const { store } = installChromeMock();
    let full = false;
    for (let i = 0; i < BUFFER_CAP; i++) {
      full = await enqueueEvent(makeEvent(`e-${i}`));
    }
    expect(full).toBe(true);
    expect((store[BUFFER_KEY] as BehaviorEvent[]).length).toBe(BUFFER_CAP);
  });

  it("evicts the oldest event past the cap", async () => {
    const { store } = installChromeMock();
    for (let i = 0; i < BUFFER_CAP + 5; i++) {
      await enqueueEvent(makeEvent(`e-${i}`));
    }
    const stored = store[BUFFER_KEY] as BehaviorEvent[];
    expect(stored.length).toBe(BUFFER_CAP);
    expect(stored[0].event_id).toBe("e-5");
  });

  it("claims a snapshot without clearing storage (at-least-once)", async () => {
    // claim 不得在投递成功前销毁事件：MV3 SW 可能在删除后、POST 完成前被杀，
    // 整批丢失。快照语义 + 成功后按 event_id 移除，把投递升级为 at-least-once。
    const { store } = installChromeMock();
    await enqueueEvent(makeEvent("e-1"));
    await enqueueEvent(makeEvent("e-2"));
    const claimed = await claimBuffer();
    expect(claimed.map((event) => event.event_id)).toEqual(["e-1", "e-2"]);
    expect((store[BUFFER_KEY] as BehaviorEvent[]).map((e) => e.event_id)).toEqual([
      "e-1",
      "e-2",
    ]);
  });

  it("removes only the flushed events on success", async () => {
    const { store } = installChromeMock();
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true })));
    await enqueueEvent(makeEvent("e-1"));
    await enqueueEvent(makeEvent("e-2"));
    const claimed = await claimBuffer();
    await enqueueEvent(makeEvent("e-3"));
    await flushBuffer(claimed);
    const stored = store[BUFFER_KEY] as BehaviorEvent[];
    expect(stored.map((event) => event.event_id)).toEqual(["e-3"]);
  });

  it("flushes the claimed batch to the backend on success", async () => {
    const { store } = installChromeMock();
    const fetchMock = vi.fn(
      async (_input: unknown, _init?: RequestInit) => ({ ok: true }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await enqueueEvent(makeEvent("e-1"));
    const batch = await claimBuffer();
    await flushBuffer(batch);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8420/api/events",
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse(String(fetchMock.mock.calls[0]![1]!.body));
    expect(body.events).toHaveLength(1);
    expect(store[BUFFER_KEY]).toBeUndefined();
  });

  it("retains the batch in storage when the backend rejects it", async () => {
    const { store } = installChromeMock();
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false })));
    await enqueueEvent(makeEvent("e-1"));
    await flushBuffer(await claimBuffer());
    const stored = store[BUFFER_KEY] as BehaviorEvent[];
    expect(stored.map((event) => event.event_id)).toEqual(["e-1"]);
  });

  it("retains the batch in storage when the network fails", async () => {
    const { store } = installChromeMock();
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }));
    await enqueueEvent(makeEvent("e-1"));
    await flushBuffer(await claimBuffer());
    const stored = store[BUFFER_KEY] as BehaviorEvent[];
    expect(stored.map((event) => event.event_id)).toEqual(["e-1"]);
  });
});
