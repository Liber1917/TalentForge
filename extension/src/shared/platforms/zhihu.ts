// Zhihu platform adapter — page-type heuristics, content-id extraction, and
// action recognition specific to zhihu.com. Plugged into the generic
// collector kernel for read-only passive collection.
import type { PlatformAdapter } from "../types";

const QUESTION_IN_PATH = /\/question\/(\d+)/;
const ARTICLE_IN_PATH = /\/p\/(\d+)/;
const CARD_SELECTOR = ".List-item";

function normalizeText(target: Element | null): string {
  if (!target) return "";
  const parts = [
    target.textContent ?? "",
    target.getAttribute("aria-label") ?? "",
    typeof target.className === "string" ? target.className : "",
  ];
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

export function detectZhihuPageType(url: string): string {
  if (url.includes("/question/")) return "question";
  if (url.includes("/p/")) return "article";
  if (url.includes("/search") || url.includes("/zsearch")) return "search";
  return "other";
}

export function extractZhihuContentId(url: string): string | null {
  const question = url.match(QUESTION_IN_PATH);
  if (question?.[1]) return question[1];
  const article = url.match(ARTICLE_IN_PATH);
  if (article?.[1]) return article[1];
  return null;
}

export function inferZhihuActionType(target: Element | null): string | null {
  const text = normalizeText(target);
  if (text.includes("赞同")) return "like";
  if (text.includes("收藏")) return "favorite";
  if (text.includes("评论")) return "comment";
  if (text.includes("关注")) return "like";
  if (target?.closest(CARD_SELECTOR)) return "click";
  return null;
}

export const ZHIHU_ADAPTER: PlatformAdapter = {
  sourcePlatform: "zhihu",
  detectPageType: detectZhihuPageType,
  extractContentId: extractZhihuContentId,
  cardSelector: CARD_SELECTOR,
  inferActionType: inferZhihuActionType,
  buildEventMetadata(url: string): Record<string, unknown> {
    return { content_id: extractZhihuContentId(url) };
  },
};
