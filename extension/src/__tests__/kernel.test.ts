// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { SCROLL_THROTTLE_MS, startCollector } from "../content/kernel";
import type { PlatformAdapter } from "../shared/types";

function makeAdapter(overrides?: Partial<PlatformAdapter>): PlatformAdapter {
  return {
    sourcePlatform: "bilibili",
    detectPageType: (url) => (url.includes("/search") ? "search" : "video"),
    extractContentId: (url) => {
      const match = url.match(/BV[\w]+/);
      return match ? match[0] : null;
    },
    cardSelector: ".card",
    inferActionType: (target) =>
      target?.closest("[data-action]")?.getAttribute("data-action") ?? null,
    buildEventMetadata: () => ({ platform: "bilibili" }),
    ...overrides,
  };
}

function installChromeMock(): ReturnType<typeof vi.fn> {
  const sendMessage = vi.fn();
  vi.stubGlobal("chrome", { runtime: { sendMessage } });
  return sendMessage;
}

describe("kernel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("emits a BEHAVIOR_EVENT on a click with a recognized action", () => {
    const sendMessage = installChromeMock();
    document.body.innerHTML = '<button id="like" data-action="like">赞</button>';
    const collector = startCollector(makeAdapter());
    document.getElementById("like")!.click();
    expect(sendMessage).toHaveBeenCalledTimes(1);
    const [message] = sendMessage.mock.calls[0];
    expect(message.action).toBe("BEHAVIOR_EVENT");
    expect(message.data.type).toBe("like");
    expect(message.data.source_platform).toBe("bilibili");
    expect(message.data.url).toBe(window.location.href);
    expect(message.data.context.pageType).toBe("video");
    expect(message.data.metadata.platform).toBe("bilibili");
    expect(typeof message.data.event_id).toBe("string");
    expect(message.data.timestamp).toBeTruthy();
    collector.dispose();
  });

  it("does not emit when the adapter recognizes no action", () => {
    const sendMessage = installChromeMock();
    document.body.innerHTML = '<div id="plain">no action</div>';
    const collector = startCollector(makeAdapter());
    document.getElementById("plain")!.click();
    expect(sendMessage).not.toHaveBeenCalled();
    collector.dispose();
  });

  it("throttles scroll events to one leading + one trailing per window", () => {
    vi.useFakeTimers();
    const sendMessage = installChromeMock();
    const collector = startCollector(makeAdapter());
    for (let i = 0; i < 10; i++) {
      window.dispatchEvent(new Event("scroll"));
    }
    expect(sendMessage).toHaveBeenCalledTimes(1);
    expect(sendMessage.mock.calls[0][0].data.type).toBe("scroll");
    vi.advanceTimersByTime(SCROLL_THROTTLE_MS);
    expect(sendMessage).toHaveBeenCalledTimes(2);
    collector.dispose();
  });

  it("emits a search event on navigation to a search page", () => {
    vi.useFakeTimers();
    const sendMessage = installChromeMock();
    const collector = startCollector(makeAdapter());
    history.pushState({}, "", "/search?q=vue");
    vi.advanceTimersByTime(2_000);
    expect(sendMessage).toHaveBeenCalledTimes(1);
    const [message] = sendMessage.mock.calls[0];
    expect(message.data.type).toBe("search");
    expect(message.data.metadata.query).toBe("vue");
    collector.dispose();
    vi.useRealTimers();
  });

  it("dispose removes listeners so no further events are emitted", () => {
    const sendMessage = installChromeMock();
    document.body.innerHTML = '<button data-action="like">赞</button>';
    const collector = startCollector(makeAdapter());
    collector.dispose();
    document.querySelector("button")!.click();
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("swallows a rejected sendMessage promise instead of leaving it unhandled", async () => {
    // Chrome 99+/Firefox return a Promise from sendMessage when no callback is
    // passed (e.g. "port closed" on Firefox event-page unload).
    const sendMessage = vi.fn(() => Promise.reject(new Error("port closed")));
    vi.stubGlobal("chrome", { runtime: { sendMessage } });
    document.body.innerHTML = '<button id="like" data-action="like">赞</button>';
    const collector = startCollector(makeAdapter());
    document.getElementById("like")!.click();
    await new Promise((resolve) => setTimeout(resolve, 0)); // 让潜在的 unhandled rejection 暴露
    expect(sendMessage).toHaveBeenCalledTimes(1);
    collector.dispose();
  });
});
