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
import { backendEndpoint } from "../shared/backend-endpoint";

const WAPI_PAGE_URL = "/wapi/zpgeek/search/joblist.json";
const sentUrls = new Set<string>();

function postJobs(jobs: unknown[]): void {
  if (jobs.length === 0) return;
  fetch(`${backendEndpoint()}/jobs/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source: "boss", jobs }),
  }).catch(() => {
    // Backend down — drop the batch; next scroll/URL change re-harvests.
  });
}

/** Debug telemetry: report harvest outcomes to the backend log (troubleshoot only). */
function reportDiagnostic(kind: string, detail: Record<string, unknown>): void {
  try {
    fetch(`${backendEndpoint()}/debug`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: "boss",
        kind,
        url: window.location.href.slice(0, 120),
        ...detail,
        at: new Date().toISOString(),
      }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    // telemetry is best-effort
  }
}

/** wapi channel: same-origin fetch of the job-list JSON (cookies+stoken auto). */
async function harvestViaWapi(): Promise<void> {
  const params = buildWapiParams(window.location.href);
  try {
    const res = await fetch(`${WAPI_PAGE_URL}?${params.toString()}`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    reportDiagnostic("wapi", { status: res.status });
    if (!res.ok) return;
    const body = (await res.json()) as Record<string, unknown>;
    const zpData = (body.zpData ?? {}) as Record<string, unknown>;
    const rawList = Array.isArray(zpData.jobList) ? zpData.jobList : [];
    const mapped = mapWapiJobList(body);
    reportDiagnostic("wapi-body", {
      code: body.code,
      listLen: rawList.length,
      mapped,
      sample: rawList.length > 0 ? Object.keys(rawList[0] as object).slice(0, 25) : [],
    });
    const fresh = mapped.filter((job) => !sentUrls.has(job.url));
    for (const job of fresh) sentUrls.add(job.url);
    reportDiagnostic("wapi-post", { fresh: fresh.length });
    postJobs(fresh);
  } catch (err) {
    reportDiagnostic("wapi-error", { msg: String(err).slice(0, 120) });
  }
}

/** DOM channel fallback: harvest visible cards from the page. */
function harvestDom(): void {
  const all = collectVisibleJobs();
  const fresh = all.filter((job) => !sentUrls.has(job.url));
  for (const job of fresh) sentUrls.add(job.url);
  reportDiagnostic("dom", { cards: all.length, fresh });
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
}
window.addEventListener("scroll", () => harvestDom(), { passive: true });

(globalThis as Record<string, unknown>).__talentforge_boss = true;
