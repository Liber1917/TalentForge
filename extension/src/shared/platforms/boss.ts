// Boss platform adapter + content collector (D25 active collection).
// Two harvest channels, both run in the user's real logged-in browser:
//   A. wapi path — same-origin fetch of the job-list JSON API. Cookies and
//      __zp_stoken__ attach automatically; salary arrives as plain text.
//      Only available on the new SPA page (/web/geek/job).
//   B. DOM path — parses visible job cards (both new and legacy page formats),
//      as a fallback for pages where the wapi path is unavailable.
// Harvest triggers on load, scroll, and SPA URL changes (no strict path guard:
// legacy search pages like /c<city>-p<position>/ don't contain /web/geek/job).

const WAPI_PATH = "/wapi/zpgeek/search/joblist.json";

export const DOM_CARD_SELECTORS = [
  ".job-card-wrapper", // new SPA cards
  "li.job-card", // legacy list cards
];

export const DOM_NAME_SELECTORS = ".job-name, .job-title, .job-primary .name, span[title]";
export const DOM_COMPANY_SELECTORS = ".company-name, .boss-name, .company-text";
export const DOM_LOCATION_SELECTORS = ".company-location, .job-area, .company-city";
export const DOM_SALARY_SELECTORS = ".salary, .job-salary, .red, .job-primary .red";

export interface BossJobCard {
  title: string;
  company: string;
  location: string;
  salary: string;
  url: string;
  tags: string[];
  description: string;
}

function textOf(el: Element | null): string {
  return (el?.textContent ?? "").replace(/\s+/g, " ").trim();
}

/** Extract city code from either URL format: ?city=101280600 or /c101280600-p100103/. */
export function extractCityCode(url: string): string | null {
  try {
    const params = new URL(url).searchParams;
    const city = params.get("city");
    if (city && /^\d{9}$/.test(city)) return city;
  } catch {
    // malformed URL — fall through to path match
  }
  const path = new URL(url, "https://www.zhipin.com").pathname;
  const match = path.match(/\/c(\d{9})/);
  return match?.[1] ?? null;
}

/** Extract the search keyword from either URL format: ?query=/wd= or legacy path. */
export function extractSearchQuery(url: string): string | null {
  try {
    const params = new URL(url).searchParams;
    for (const key of ["query", "wd", "keyword"]) {
      const value = params.get(key);
      if (value) return value;
    }
  } catch {
    // malformed URL — ignore
  }
  return null;
}

/** True when the URL is a search page in either format. */
export function isSearchPage(url: string): boolean {
  return (
    url.includes("/web/geek/job") ||
    /\/c\d{9}-p\d+/.test(new URL(url, "https://www.zhipin.com").pathname)
  );
}

/** Map a wapi job-list record to the normalized card shape. */
export function mapWapiJob(item: Record<string, unknown>): BossJobCard | null {
  const jobId = String(item.jobId ?? item.job_id ?? "");
  const title = String(item.jobName ?? item.job_name ?? item.title ?? "").trim();
  if (!jobId || !title) return null;
  const labels = Array.isArray(item.jobLabels) ? item.jobLabels.map(String) : [];
  return {
    title: title.slice(0, 120),
    company: String(item.brandName ?? item.brand_name ?? "").slice(0, 80),
    location: [
      String(item.cityName ?? ""),
      String(item.areaDistrict ?? item.district ?? ""),
    ]
      .filter(Boolean)
      .join("·")
      .slice(0, 60),
    salary: String(item.salaryDesc ?? item.salary ?? "").slice(0, 40),
    url: `https://www.zhipin.com/job_detail/${jobId}.html`,
    tags: labels.slice(0, 10),
    description: String(item.jobDetail ?? "").slice(0, 500),
  };
}

/** Map a wapi joblist.json payload body to normalized cards (deduped by url). */
export function mapWapiJobList(body: Record<string, unknown>): BossJobCard[] {
  const zpData = (body.zpData ?? {}) as Record<string, unknown>;
  const list = Array.isArray(zpData.jobList) ? zpData.jobList : [];
  const seen = new Set<string>();
  const jobs: BossJobCard[] = [];
  for (const raw of list) {
    const item = (raw ?? {}) as Record<string, unknown>;
    const job = mapWapiJob(item);
    if (job && !seen.has(job.url)) {
      seen.add(job.url);
      jobs.push(job);
    }
  }
  return jobs;
}

/** DOM channel: collect visible job cards from the page (deduped by url). */
export function collectVisibleJobs(root: ParentNode = document): BossJobCard[] {
  const seen = new Set<string>();
  const jobs: BossJobCard[] = [];
  for (const selector of DOM_CARD_SELECTORS) {
    for (const card of root.querySelectorAll(selector)) {
      const link = card.querySelector("a[href*='/job_detail/']");
      const href = link?.getAttribute("href") ?? "";
      if (!href) continue;
      const url = href.startsWith("http") ? href : `https://www.zhipin.com${href}`;
      const title =
        textOf(card.querySelector(DOM_NAME_SELECTORS)) ||
        textOf(card.querySelector("a[href*='/job_detail/'] span")) ||
        textOf(link);
      if (!title || seen.has(url)) continue;
      seen.add(url);
      jobs.push({
        title: title.slice(0, 120),
        company: textOf(card.querySelector(DOM_COMPANY_SELECTORS)).slice(0, 80),
        location: textOf(card.querySelector(DOM_LOCATION_SELECTORS)).slice(0, 60),
        salary: textOf(card.querySelector(DOM_SALARY_SELECTORS)).slice(0, 40),
        url,
        tags: [...card.querySelectorAll(".tag-list li, .job-tags span, .tags li")]
          .map((t) => textOf(t))
          .filter(Boolean)
          .slice(0, 10),
        description: textOf(card).slice(0, 500),
      });
    }
  }
  return jobs;
}
