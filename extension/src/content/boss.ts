// Boss content-script entry (document_idle). ACTIVE collector per D25:
// harvests job cards via the wapi channel (new SPA page) with a DOM fallback,
// posts deduped batches to /api/jobs/batch. No strict URL guard — runs on
// load, scroll, and SPA URL changes so both /web/geek/job and legacy
// /c<city>-p<position>/ search pages are covered.
import {
  buildWapiParams,
  collectVisibleJobs,
  isSearchPage,
  mapWapiJobList,
} from "../shared/platforms/boss";
import { reportJobs } from "../shared/jobs_report";
import { createAssistToggle, createScrollPulse } from "../shared/scroll-pulse";

const WAPI_PAGE_URL = "/wapi/zpgeek/search/joblist.json";
const sentUrls = new Set<string>();

function postJobs(jobs: unknown[]): void {
  reportJobs("boss", jobs as Parameters<typeof reportJobs>[1]);
}

/** wapi channel: same-origin fetch of the job-list JSON (cookies+stoken auto). */
async function harvestViaWapi(): Promise<void> {
  const params = buildWapiParams(window.location.href);
  try {
    const res = await fetch(`${WAPI_PAGE_URL}?${params.toString()}`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return;
    const body = (await res.json()) as Record<string, unknown>;
    const mapped = mapWapiJobList(body);
    const fresh = mapped.filter((job) => !sentUrls.has(job.url));
    for (const job of fresh) sentUrls.add(job.url);
    postJobs(fresh);
  } catch (err) {
    // 采集失败静默：下一轮 scroll/URL 变化重试
  }
}

/** DOM channel fallback: harvest visible cards from the page. */
function harvestDom(): void {
  const all = collectVisibleJobs();
  const fresh = all.filter((job) => !sentUrls.has(job.url));
  for (const job of fresh) sentUrls.add(job.url);
  postJobs(fresh);
}

// SPA navigation watch: content scripts run in an isolated world — patching
// history.pushState here does NOT intercept the page's own SPA navigation
// (the page world calls its unpatched original). Poll location.href instead.
let currentUrl = window.location.href;
function onUrlChanged(): void {
  const next = window.location.href;
  if (next === currentUrl) return;
  currentUrl = next;
  if (isSearchPage(next)) {
    void harvestViaWapi();
    harvestDom();
  }
}
window.setInterval(onUrlChanged, 1_500);
window.addEventListener("popstate", onUrlChanged);

// ---- wiring ----
if (isSearchPage(window.location.href)) {
  void harvestViaWapi();
  harvestDom();
  setupAssist();
}
window.addEventListener("scroll", () => harvestDom(), { passive: true });

function setupAssist(): void {
  const pulse = createScrollPulse({
    scrollBy: (step) => {
      window.scrollBy({ top: step, behavior: "smooth" });
    },
    measure: () => ({
      scrollY: window.scrollY,
      viewportH: window.innerHeight,
      docH: document.documentElement.scrollHeight,
    }),
    delay: (ms) => new Promise<void>((resolve) => setTimeout(resolve, ms)),
  });
  createAssistToggle(document, () => {
    if (pulse.isRunning()) {
      pulse.stop();
    } else {
      void pulse.runToBottom();
    }
  });
}

(globalThis as Record<string, unknown>).__talentforge_boss = true;
