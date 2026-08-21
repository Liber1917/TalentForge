// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { BILIBILI_ADAPTER } from "../shared/platforms/bilibili";
import { ZHIHU_ADAPTER } from "../shared/platforms/zhihu";

function element(html: string): HTMLElement {
  const container = document.createElement("div");
  container.innerHTML = html;
  return container.firstElementChild as HTMLElement;
}

describe("bilibili adapter", () => {
  it("detects page types", () => {
    expect(BILIBILI_ADAPTER.detectPageType("https://www.bilibili.com/video/BV1xx411c7mD")).toBe(
      "video",
    );
    expect(BILIBILI_ADAPTER.detectPageType("https://space.bilibili.com/123456")).toBe("space");
    expect(
      BILIBILI_ADAPTER.detectPageType("https://search.bilibili.com/all?keyword=vue"),
    ).toBe("search");
    expect(BILIBILI_ADAPTER.detectPageType("https://www.bilibili.com/")).toBe("other");
  });

  it("extracts a bvid from the path or query", () => {
    expect(BILIBILI_ADAPTER.extractContentId("https://www.bilibili.com/video/BV1xx411c7mD")).toBe(
      "BV1xx411c7mD",
    );
    expect(
      BILIBILI_ADAPTER.extractContentId("https://www.bilibili.com/video?bvid=BV1xx411c7mD"),
    ).toBe("BV1xx411c7mD");
    expect(BILIBILI_ADAPTER.extractContentId("https://www.bilibili.com/")).toBeNull();
  });

  it("infers like from a 点赞 button", () => {
    const like = element('<button class="like-btn" aria-label="点赞">赞</button>');
    expect(BILIBILI_ADAPTER.inferActionType(like)).toBe("like");
  });

  it("infers click from inside a video card", () => {
    const card = element(
      '<div class="bili-video-card"><a href="/video/BV1xx411c7mD">title</a></div>',
    );
    const link = card.querySelector("a");
    expect(BILIBILI_ADAPTER.inferActionType(link)).toBe("click");
  });

  it("returns null for unrelated targets", () => {
    const div = element("<div>some plain text</div>");
    expect(BILIBILI_ADAPTER.inferActionType(div)).toBeNull();
    expect(BILIBILI_ADAPTER.inferActionType(null)).toBeNull();
  });

  it("builds event metadata with the bvid as content_id", () => {
    expect(
      BILIBILI_ADAPTER.buildEventMetadata("https://www.bilibili.com/video/BV1xx411c7mD"),
    ).toEqual({ content_id: "BV1xx411c7mD" });
  });
});

describe("zhihu adapter", () => {
  it("detects page types", () => {
    expect(ZHIHU_ADAPTER.detectPageType("https://www.zhihu.com/question/123456")).toBe("question");
    expect(ZHIHU_ADAPTER.detectPageType("https://zhuanlan.zhihu.com/p/987654")).toBe("article");
    expect(ZHIHU_ADAPTER.detectPageType("https://www.zhihu.com/search?q=vue")).toBe("search");
    expect(ZHIHU_ADAPTER.detectPageType("https://www.zhihu.com/")).toBe("other");
  });

  it("extracts question and article ids", () => {
    expect(ZHIHU_ADAPTER.extractContentId("https://www.zhihu.com/question/123456")).toBe("123456");
    expect(
      ZHIHU_ADAPTER.extractContentId("https://www.zhihu.com/question/123456/answer/999"),
    ).toBe("123456");
    expect(ZHIHU_ADAPTER.extractContentId("https://zhuanlan.zhihu.com/p/987654")).toBe("987654");
    expect(ZHIHU_ADAPTER.extractContentId("https://www.zhihu.com/")).toBeNull();
  });

  it("infers like from a 赞同 button", () => {
    const agree = element('<button class="VoteButton" aria-label="赞同">赞同</button>');
    expect(ZHIHU_ADAPTER.inferActionType(agree)).toBe("like");
  });

  it("infers comment from a 评论 button", () => {
    const comment = element('<button aria-label="评论">评论</button>');
    expect(ZHIHU_ADAPTER.inferActionType(comment)).toBe("comment");
  });

  it("infers click from inside a list item", () => {
    const item = element(
      '<div class="List-item"><a href="/question/123456">some question</a></div>',
    );
    const link = item.querySelector("a");
    expect(ZHIHU_ADAPTER.inferActionType(link)).toBe("click");
  });

  it("returns null for unrelated targets", () => {
    const div = element("<div>unrelated</div>");
    expect(ZHIHU_ADAPTER.inferActionType(div)).toBeNull();
  });

  it("builds event metadata with the question id as content_id", () => {
    expect(
      ZHIHU_ADAPTER.buildEventMetadata("https://www.zhihu.com/question/123456"),
    ).toEqual({ content_id: "123456" });
  });
});

describe("content entry smoke", () => {
  it("bilibili entry imports and boots the collector without crashing", async () => {
    await import("../content/bilibili");
    expect(
      (globalThis as Record<string, unknown>).__talentforge_bilibili,
    ).toBe(true);
  });

  it("zhihu entry imports and boots the collector without crashing", async () => {
    await import("../content/zhihu");
    expect(
      (globalThis as Record<string, unknown>).__talentforge_zhihu,
    ).toBe(true);
  });
});
