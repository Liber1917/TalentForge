// Boss content-script entry (document_idle). ACTIVE collector per D25:
// on job-search pages it harvests visible job cards (auto + on scroll)
// and posts deduped batches to /api/jobs/batch on the local backend.
import { collectVisibleJobs } from "../shared/platforms/boss";
import { backendEndpoint } from "../shared/backend-endpoint";

const FLUSH_DEBOUNCE_MS = 1_500;
const sentUrls = new Set<string>();

function postJobs(jobs: unknown[]): Promise<void> {
  return fetch(`${backendEndpoint()}/jobs/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source: "boss", jobs }),
  })
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    })
    .catch(() => {
      // Backend down — drop the batch; the next scroll re-harvests anyway.
    });
}

let timer: number | null = null;

function harvest(): void {
  const fresh = collectVisibleJobs().filter((job) => !sentUrls.has(job.url));
  if (fresh.length === 0) return;
  for (const job of fresh) sentUrls.add(job.url);
  if (timer !== null) window.clearTimeout(timer);
  timer = window.setTimeout(() => {
    timer = null;
    void postJobs(fresh);
  }, FLUSH_DEBOUNCE_MS);
}

if (window.location.pathname.includes("/web/geek/job")) {
  harvest();
  window.addEventListener("scroll", () => harvest(), { passive: true });
}

(globalThis as Record<string, unknown>).__talentforge_boss = true;
