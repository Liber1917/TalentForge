// 智联 content script（M11 auto 通道，isolated world）：
// 监听 MAIN-world hook 的 postMessage（fe-api 响应）→ mapFeApiItem 映射 →
// service worker 中转上报（无 Origin/PNA 问题）。
import { reportJobs } from "../shared/jobs_report";
import {
  ZHAOPIN_HOOK_MARKER,
  isZhaopinSearchUrl,
  mapFeApiItem,
  type ZpJobCard,
} from "../shared/platforms/zhaopin";

const sentUrls = new Set<string>();

function postJobs(cards: ZpJobCard[]): void {
  reportJobs("zhaopin", cards);
}

window.addEventListener("message", (event: MessageEvent) => {
  if (!event.origin.endsWith("zhaopin.com")) return;
  const data = event.data as
    | { type?: string; data?: { data?: { results?: unknown[] } } }
    | null;
  if (data?.type !== ZHAOPIN_HOOK_MARKER) return;
  if (!isZhaopinSearchUrl(window.location.href)) return;
  const results = data.data?.data?.results;
  if (!Array.isArray(results)) return;
  const cards = results
    .map(mapFeApiItem)
    .filter((card): card is ZpJobCard => card !== null && card.url !== "" && !sentUrls.has(card.url));
  for (const card of cards) sentUrls.add(card.url);
  postJobs(cards);
});

(globalThis as Record<string, unknown>).__talentforge_zhaopin = true;
