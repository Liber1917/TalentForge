// Content-script collector kernel: wires a PlatformAdapter to DOM observers and
// emits BehaviorEvents. Read-only passive collection — no hover/video-dwell
// observers, no writes.
import { newEventId } from "../shared/types";
import type { BehaviorEvent, PlatformAdapter } from "../shared/types";

export const SCROLL_THROTTLE_MS = 500;

export interface Collector {
  dispose(): void;
}

type HistoryMethod = "pushState" | "replaceState";

function sendMessage(msg: unknown): void {
  try {
    const chromeApi = (
      globalThis as { chrome?: { runtime?: { sendMessage?: (message: unknown) => void } } }
    ).chrome;
    chromeApi?.runtime?.sendMessage?.(msg);
  } catch {
    // No runtime sender available (e.g. unit tests) — collection is best-effort.
  }
}

function closestHref(target: Element | null): string | null {
  const link = target?.closest("a");
  if (!link) return null;
  return link.getAttribute("href");
}

function extractSearchQuery(url: string): string | null {
  try {
    const params = new URL(url).searchParams;
    for (const key of ["q", "query", "keyword", "wd"]) {
      const value = params.get(key);
      if (value) return value;
    }
  } catch {
    // Malformed URL — ignore.
  }
  return null;
}

export function startCollector(adapter: PlatformAdapter): Collector {
  const win = window;
  const doc = document;
  let currentUrl = win.location.href;
  let scrollTimer: number | null = null;
  let lastScrollAt = 0;
  const originalHistoryMethods = new Map<HistoryMethod, History["pushState"]>();

  const buildEvent = (
    type: string,
    metadata: Record<string, unknown> = {},
  ): BehaviorEvent => {
    const url = win.location.href;
    const contentId = adapter.extractContentId(url);
    return {
      event_id: newEventId(),
      type,
      url,
      title: doc.title || "",
      timestamp: new Date().toISOString(),
      source_platform: adapter.sourcePlatform,
      context: {
        pageType: adapter.detectPageType(url),
        viewport: { width: win.innerWidth, height: win.innerHeight },
        scrollPosition: { x: win.scrollX, y: win.scrollY },
      },
      metadata: {
        ...adapter.buildEventMetadata(url),
        ...(contentId ? { content_id: contentId } : {}),
        ...metadata,
      },
    };
  };

  const sendEvent = (type: string, metadata: Record<string, unknown> = {}): void => {
    sendMessage({ action: "BEHAVIOR_EVENT", data: buildEvent(type, metadata) });
  };

  const handleClick = (event: MouseEvent): void => {
    const target = event.target instanceof Element ? (event.target as Element) : null;
    const actionType = adapter.inferActionType(target);
    if (!actionType) return;
    sendEvent(actionType, {
      tagName: target?.tagName ?? null,
      text: target?.textContent?.trim().slice(0, 100) ?? null,
      href: closestHref(target),
    });
  };

  const handleScroll = (): void => {
    const now = Date.now();
    const remaining = SCROLL_THROTTLE_MS - (now - lastScrollAt);
    if (remaining <= 0) {
      lastScrollAt = now;
      sendEvent("scroll", { scrollY: win.scrollY });
    } else if (scrollTimer === null) {
      scrollTimer = win.setTimeout(() => {
        scrollTimer = null;
        lastScrollAt = Date.now();
        sendEvent("scroll", { scrollY: win.scrollY });
      }, remaining);
    }
  };

  const maybeEmitSearch = (url: string): void => {
    if (adapter.detectPageType(url) !== "search") return;
    const query = extractSearchQuery(url);
    sendEvent("search", { ...(query ? { query } : {}) });
  };

  const handleUrlChange = (): void => {
    const nextUrl = win.location.href;
    if (nextUrl === currentUrl) return;
    currentUrl = nextUrl;
    maybeEmitSearch(nextUrl);
  };

  const handlePopState = (): void => {
    handleUrlChange();
  };

  const patchHistoryMethod = (method: HistoryMethod): void => {
    const original = history[method].bind(history);
    originalHistoryMethods.set(method, history[method]);
    history[method] = function patched(
      this: History,
      ...args: Parameters<History["pushState"]>
    ): ReturnType<History["pushState"]> {
      const result = original.apply(this, args);
      handleUrlChange();
      return result;
    };
  };

  doc.addEventListener("click", handleClick);
  win.addEventListener("scroll", handleScroll, { passive: true });
  win.addEventListener("popstate", handlePopState);
  patchHistoryMethod("pushState");
  patchHistoryMethod("replaceState");

  const dispose = (): void => {
    doc.removeEventListener("click", handleClick);
    win.removeEventListener("scroll", handleScroll);
    win.removeEventListener("popstate", handlePopState);
    if (scrollTimer !== null) win.clearTimeout(scrollTimer);
    scrollTimer = null;
    for (const [method, original] of originalHistoryMethods) {
      history[method] = original;
    }
    originalHistoryMethods.clear();
  };

  return { dispose };
}
