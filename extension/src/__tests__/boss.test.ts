// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import {
  BOSS_SEARCH_PATH,
  JOB_CARD_SELECTOR,
  collectVisibleJobs,
  detectBossPageType,
  parseJobCard,
} from "../shared/platforms/boss";

function element(html: string): HTMLElement {
  const container = document.createElement("div");
  container.innerHTML = html;
  return container.firstElementChild as HTMLElement;
}

const CARD_HTML = `
<div class="job-card-wrapper">
  <a class="job-card-left" href="/job_detail/abc123.html?lid=x">
    <span class="job-name">Python 后端工程师</span>
    <span class="salary">25-50K·16薪</span>
  </a>
  <div class="company-name">星辰科技</div>
  <div class="company-location">深圳·南山区</div>
  <ul class="tag-list"><li>Python</li><li>分布式</li></ul>
</div>`;

describe("boss adapter", () => {
  it("detects page types", () => {
    expect(detectBossPageType(`https://www.zhipin.com${BOSS_SEARCH_PATH}?query=x`)).toBe(
      "job-search",
    );
    expect(detectBossPageType("https://www.zhipin.com/job_detail/abc.html")).toBe("job-detail");
    expect(detectBossPageType("https://www.zhipin.com/")).toBe("other");
  });

  it("parses a job card into the normalized shape", () => {
    const card = element(CARD_HTML);
    const job = parseJobCard(card);
    expect(job).not.toBeNull();
    expect(job?.title).toBe("Python 后端工程师");
    expect(job?.company).toBe("星辰科技");
    expect(job?.salary).toBe("25-50K·16薪");
    expect(job?.url).toBe("https://www.zhipin.com/job_detail/abc123.html?lid=x");
    expect(job?.tags).toEqual(["Python", "分布式"]);
  });

  it("rejects cards without title or link (ads / skeletons)", () => {
    expect(parseJobCard(element('<div class="job-card-wrapper"><span></span></div>'))).toBeNull();
    expect(parseJobCard(element('<div class="job-card-wrapper">促销</div>'))).toBeNull();
  });

  it("collects visible jobs deduped by url", () => {
    document.body.innerHTML = `${CARD_HTML}${CARD_HTML}`;
    const jobs = collectVisibleJobs(document.body);
    expect(jobs).toHaveLength(1);
    expect(jobs[0]?.title).toBe("Python 后端工程师");
  });

  it("uses the job-card selector contract", () => {
    expect(JOB_CARD_SELECTOR).toContain(".job-card-wrapper");
    expect(JOB_CARD_SELECTOR).toContain("li.job-card");
  });
});
