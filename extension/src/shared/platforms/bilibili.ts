// Bilibili platform adapter — page-type heuristics, bvid extraction, and
// action recognition specific to bilibili.com. Plugged into the generic
// collector kernel for read-only passive collection.
import type { PlatformAdapter } from "../types";

const BV_IN_PATH = /\/video\/(BV[0-9A-Za-z]+)/;
const BV_ANYWHERE = /BV[0-9A-Za-z]{10}/;
const CARD_SELECTOR = ".bili-video-card";

function normalizeText(target: Element | null): string {
  if (!target) return "";
  const parts = [
    target.textContent ?? "",
    target.getAttribute("aria-label") ?? "",
    typeof target.className === "string" ? target.className : "",
  ];
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

export function detectBilibiliPageType(url: string): string {
  if (url.includes("/video/") || BV_ANYWHERE.test(url)) return "video";
  if (url.includes("/space/") || url.includes("space.bilibili.com")) return "space";
  if (url.includes("/search") || url.includes("/all/search")) return "search";
  return "other";
}

export function extractBvid(url: string): string | null {
  const pathMatch = url.match(BV_IN_PATH);
  if (pathMatch?.[1]) return pathMatch[1];
  try {
    const queryBvid = new URL(url).searchParams.get("bvid");
    if (queryBvid) return queryBvid;
  } catch {
    // Malformed URL — fall through to null.
  }
  return null;
}

export function inferBilibiliActionType(target: Element | null): string | null {
  const text = normalizeText(target);
  if (text.includes("点赞") || text.includes("三连")) return "like";
  if (text.includes("投币")) return "favorite";
  if (text.includes("收藏")) return "favorite";
  if (target?.closest(CARD_SELECTOR)) return "click";
  return null;
}

export const BILIBILI_ADAPTER: PlatformAdapter = {
  sourcePlatform: "bilibili",
  detectPageType: detectBilibiliPageType,
  extractContentId: extractBvid,
  cardSelector: CARD_SELECTOR,
  inferActionType: inferBilibiliActionType,
  buildEventMetadata(url: string): Record<string, unknown> {
    return { content_id: extractBvid(url) };
  },
};
