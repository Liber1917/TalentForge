// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ZHAOPIN_HOOK_MARKER,
  installZhaopinHook,
  isFeApiUrl,
  isZhaopinSearchUrl,
  mapFeApiItem,
} from "../shared/platforms/zhaopin";

const API_ITEM = {
  number: "CZ123456789",
  name: "Python开发工程师",
  company: { name: "示例科技" },
  city: { name: "上海" },
  district: { name: "浦东新区" },
  salary60: { from: 20, to: 35 },
  welfare: ["五险一金", "弹性工作"],
  skills: ["Python", "Docker"],
};

describe("mapFeApiItem", () => {
  it("maps a fe-api /c/i/sou item to a job card", () => {
    const card = mapFeApiItem(API_ITEM)!;
    expect(card.title).toBe("Python开发工程师");
    expect(card.company).toBe("示例科技");
    expect(card.location).toBe("上海·浦东新区");
    expect(card.salary).toBe("20-35K/月");
    expect(card.url).toBe("https://jobs.zhaopin.com/CZ123456789.htm");
    expect(card.tags).toEqual(["五险一金", "弹性工作", "Python", "Docker"]);
    expect(card.description).toContain("Python");
  });

  it("falls back across field-name variants", () => {
    const card = mapFeApiItem({
      positionId: "CC99",
      jobName: "数据分析师",
      companyName: "备选公司",
      city: "杭州",
      salaryReal: "10-15K",
    })!;
    expect(card.title).toBe("数据分析师");
    expect(card.company).toBe("备选公司");
    expect(card.location).toBe("杭州");
    expect(card.salary).toBe("10-15K");
    expect(card.url).toBe("https://jobs.zhaopin.com/CC99.htm");
  });

  it("returns null without a title or valid payload", () => {
    expect(mapFeApiItem({ name: "" })).toBeNull();
    expect(mapFeApiItem("not-a-dict" as unknown as Record<string, unknown>)).toBeNull();
    expect(mapFeApiItem(null as unknown as Record<string, unknown>)).toBeNull();
  });
});

describe("isZhaopinSearchUrl", () => {
  it("matches zhaopin search surfaces", () => {
    expect(isZhaopinSearchUrl("https://sou.zhaopin.com/?jl=530&kw=python")).toBe(true);
    expect(isZhaopinSearchUrl("https://www.zhaopin.com/sou/jl530/kw01O00/p1/")).toBe(true);
    expect(isZhaopinSearchUrl("https://www.zhaopin.com/company/abc")).toBe(false);
    expect(isZhaopinSearchUrl("https://www.shixiseng.com/interns")).toBe(false);
  });
});

describe("isFeApiUrl", () => {
  it("matches only fe-api /c/i/ endpoints", () => {
    expect(isFeApiUrl("https://fe-api.zhaopin.com/c/i/sou?kw=x")).toBe(true);
    expect(isFeApiUrl("https://fe-api.zhaopin.com/c/i/search/positions")).toBe(true);
    expect(isFeApiUrl("https://fe-api.zhaopin.com/api/c/other")).toBe(false);
    expect(isFeApiUrl("https://www.zhaopin.com/")).toBe(false);
    expect(isFeApiUrl(undefined)).toBe(false);
  });
});

describe("installZhaopinHook", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    delete (window as { __tfZhaopinHooked?: boolean }).__tfZhaopinHooked;
  });

  it("wraps fetch and posts fe-api responses with the marker", async () => {
    const posted: unknown[] = [];
    const spy = vi.fn((d: unknown) => posted.push(d));
    window.postMessage = spy as unknown as typeof window.postMessage;
    const payload = { data: { results: [{ number: "Z1", name: "N" }] } };
    const resLike = { clone: () => ({ json: async () => payload }) };
    const innerFetch = vi.fn(async () => resLike as unknown as Response);
    window.fetch = innerFetch as unknown as typeof fetch;

    installZhaopinHook(window);
    await window.fetch("https://fe-api.zhaopin.com/c/i/sou?kw=x");
    await new Promise((r) => setTimeout(r, 20));

    expect(innerFetch).toHaveBeenCalledTimes(1);
    expect(posted[0]).toMatchObject({ type: ZHAOPIN_HOOK_MARKER });
    expect((posted[0] as { data: unknown }).data).toEqual(payload);

    await window.fetch("https://other.example.com/api");
    await new Promise((r) => setTimeout(r, 10));
    expect(posted).toHaveLength(1); // 非 fe-api 不上报
  });

  it("is idempotent across double install", async () => {
    const posted: unknown[] = [];
    window.postMessage = vi.fn((d: unknown) => posted.push(d)) as unknown as typeof window.postMessage;
    const payload = { data: { results: [] } };
    const resLike = { clone: () => ({ json: async () => payload }) };
    let calls = 0;
    window.fetch = vi.fn(async () => { calls += 1; return resLike as unknown as Response; }) as unknown as typeof fetch;

    installZhaopinHook(window);
    installZhaopinHook(window);
    await window.fetch("https://fe-api.zhaopin.com/c/i/sou");
    await new Promise((r) => setTimeout(r, 20));
    expect(calls).toBe(1); // fetch 只被包裹一层
    expect(posted).toHaveLength(1);
  });
});
