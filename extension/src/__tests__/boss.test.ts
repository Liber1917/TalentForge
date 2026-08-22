// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import {
  collectVisibleJobs,
  extractCityCode,
  extractSearchQuery,
  isSearchPage,
  mapWapiJob,
  mapWapiJobList,
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
  it("detects search pages in both URL formats", () => {
    expect(isSearchPage("https://www.zhipin.com/web/geek/job?query=python")).toBe(true);
    expect(isSearchPage("https://www.zhipin.com/c101280600-p100103/?query=python")).toBe(true);
    expect(isSearchPage("https://www.zhipin.com/job_detail/abc.html")).toBe(false);
    expect(isSearchPage("https://www.zhipin.com/")).toBe(false);
  });

  it("extracts city code from query param and legacy path", () => {
    expect(extractCityCode("https://www.zhipin.com/web/geek/job?city=101280600")).toBe("101280600");
    expect(extractCityCode("https://www.zhipin.com/c101280600-p100103/")).toBe("101280600");
    expect(extractCityCode("https://www.zhipin.com/")).toBeNull();
  });

  it("extracts search query from both param names", () => {
    expect(extractSearchQuery("https://www.zhipin.com/web/geek/job?query=python")).toBe("python");
    expect(extractSearchQuery("https://www.zhipin.com/c101280600-p100103/?wd=go")).toBe("go");
    expect(extractSearchQuery("https://www.zhipin.com/")).toBeNull();
  });

  it("maps a wapi record to the normalized card shape", () => {
    const job = mapWapiJob({
      jobId: "abc123",
      jobName: "Python 后端工程师",
      salaryDesc: "25-50K·16薪",
      brandName: "星辰科技",
      cityName: "深圳",
      areaDistrict: "南山区",
      jobLabels: ["Python", "分布式"],
    });
    expect(job?.title).toBe("Python 后端工程师");
    expect(job?.company).toBe("星辰科技");
    expect(job?.location).toBe("深圳·南山区");
    expect(job?.salary).toBe("25-50K·16薪");
    expect(job?.url).toBe("https://www.zhipin.com/job_detail/abc123.html");
  });

  it("rejects wapi records without jobId or title", () => {
    expect(mapWapiJob({})).toBeNull();
    expect(mapWapiJob({ jobId: "x" })).toBeNull();
    expect(mapWapiJob({ jobName: "n" })).toBeNull();
  });

  it("maps a wapi joblist payload with dedup", () => {
    const jobs = mapWapiJobList({
      zpData: {
        jobList: [
          { jobId: "a", jobName: "A" },
          { jobId: "a", jobName: "A dup" },
          { jobId: "b", jobName: "B" },
          {},
        ],
      },
    });
    expect(jobs).toHaveLength(2);
  });

  it("collects visible DOM jobs deduped by url", () => {
    document.body.innerHTML = `${CARD_HTML}${CARD_HTML}`;
    const jobs = collectVisibleJobs(document.body);
    expect(jobs).toHaveLength(1);
    expect(jobs[0]?.title).toBe("Python 后端工程师");
    expect(jobs[0]?.salary).toBe("25-50K·16薪");
  });

  it("skips cards without a job-detail link", () => {
    document.body.innerHTML = '<div class="job-card-wrapper"><span>促销</span></div>';
    expect(collectVisibleJobs(document.body)).toHaveLength(0);
  });

  it("extracts city code from query param and legacy path (edge)", () => {
    const legacy = element(CARD_HTML);
    expect(legacy.querySelector("a")?.getAttribute("href")).toContain("/job_detail/");
  });
});
