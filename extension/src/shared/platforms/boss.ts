// Boss platform adapter — job-card scraping on zhipin.com search pages.
// Unlike bilibili/zhihu (passive behavior collection), Boss is an ACTIVE
// collector: it reads job cards from the search DOM and posts normalized job
// batches to the TalentForge backend. Per D25, the server never touches
// zhipin.com — the user's real browser does the fetching.

export const BOSS_SEARCH_PATH = "/web/geek/job";

export const JOB_CARD_SELECTOR = ".job-card-wrapper, li.job-card";

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

/** Extract one normalized job card from a DOM node. Returns null when the
 *  card lacks both title and link (advertisement / skeleton). */
export function parseJobCard(card: Element): BossJobCard | null {
  const link = card.querySelector("a.job-card-left, a[href*='/job_detail/']");
  const href = link?.getAttribute("href") ?? "";
  const url = href.startsWith("http") ? href : `https://www.zhipin.com${href}`;
  const title = textOf(
    card.querySelector(".job-name, .job-title, span[title]"),
  ) || textOf(link);
  if (!title || !href) return null;
  return {
    title: title.slice(0, 120),
    company: textOf(card.querySelector(".company-name, .boss-name")).slice(0, 80),
    location: textOf(card.querySelector(".company-location, .job-area")).slice(0, 60),
    salary: textOf(card.querySelector(".salary, .job-salary")).slice(0, 40),
    url,
    tags: [...card.querySelectorAll(".tag-list li, .job-tags span")]
      .map((t) => textOf(t))
      .filter(Boolean)
      .slice(0, 10),
    description: textOf(card.querySelector(".job-desc, .job-card-inner")).slice(0, 500),
  };
}

/** Collect all job cards currently in the DOM (deduped by URL). */
export function collectVisibleJobs(root: ParentNode = document): BossJobCard[] {
  const seen = new Set<string>();
  const jobs: BossJobCard[] = [];
  for (const card of root.querySelectorAll(JOB_CARD_SELECTOR)) {
    const parsed = parseJobCard(card);
    if (parsed && !seen.has(parsed.url)) {
      seen.add(parsed.url);
      jobs.push(parsed);
    }
  }
  return jobs;
}

export function detectBossPageType(url: string): string {
  if (url.includes(BOSS_SEARCH_PATH)) return "job-search";
  if (url.includes("/job_detail/")) return "job-detail";
  return "other";
}
